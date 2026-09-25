#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import shutil
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path

try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None
    np = None


@dataclass
class VisionState:
    available: bool = False
    camera_id: str = ""
    face_present: bool = False
    face_x: float = 0.0
    face_y: float = 0.0
    face_area: float = 0.0
    stationary_seconds: float = 0.0
    five_fingers: bool = False
    right_hand_five_fingers: bool = False
    open_palm_confidence: float = 0.0
    hand_x: float = 0.0
    hand_y: float = 0.0
    preview_rgba: bytes = b""
    preview_width: int = 0
    preview_height: int = 0
    last_frame_at: float = 0.0
    error: str = ""


class CameraVision:
    """Low-rate, fully local front-camera observer.

    Termux:API exposes still capture rather than a continuous camera stream, so
    this observer intentionally runs at a modest cadence. Photos are stored only
    in Termux cache and deleted immediately after analysis.
    """

    def __init__(self, interval: float = 1.05) -> None:
        self.interval = max(0.65, interval)
        self.lock = threading.Lock()
        self.state = VisionState()

        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

        self.cache_dir = Path.home() / ".cache" / "desk-buddy" / "vision"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.capture_path = self.cache_dir / "front.jpg"

        self.face_history: deque[tuple[float, float, float]] = deque(maxlen=42)
        self.face_first_seen = 0.0
        self.last_face_at = 0.0
        self.last_bored_event = 0.0

        self.five_streak = 0
        self.right_five_streak = 0
        self.last_five_event = 0.0
        self.five_event_pending = False
        self.right_five_event_pending = False
        self.bored_event_pending = False

        self.face_detector = None
        if cv2 is not None:
            candidates: list[Path] = []

            try:
                candidates.append(
                    Path(cv2.data.haarcascades)
                    / "haarcascade_frontalface_default.xml"
                )
            except Exception:
                pass

            # Termux' packaged OpenCV may keep cascades under share/opencv4
            # instead of exposing cv2.data like PyPI wheels do.
            prefix = Path(shutil.which("python") or "/data/data/com.termux/files/usr/bin/python").parent.parent
            candidates.extend(
                [
                    prefix / "share" / "opencv4" / "haarcascades" / "haarcascade_frontalface_default.xml",
                    prefix / "share" / "opencv" / "haarcascades" / "haarcascade_frontalface_default.xml",
                ]
            )

            for cascade_path in candidates:
                try:
                    if not cascade_path.exists():
                        continue
                    detector = cv2.CascadeClassifier(str(cascade_path))
                    if not detector.empty():
                        self.face_detector = detector
                        break
                except Exception:
                    continue

    def start(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            return

        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="desk-buddy-camera",
        )
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

        if self.thread is not None:
            self.thread.join(timeout=2.0)

        try:
            self.capture_path.unlink(missing_ok=True)
        except OSError:
            pass

    def snapshot(self) -> VisionState:
        with self.lock:
            return replace(self.state)

    def consume_five_fingers(self) -> bool:
        with self.lock:
            value = self.five_event_pending
            self.five_event_pending = False
            return value

    def consume_right_hand_five(self) -> bool:
        with self.lock:
            value = self.right_five_event_pending
            self.right_five_event_pending = False
            return value

    def consume_boredom(self) -> bool:
        with self.lock:
            value = self.bored_event_pending
            self.bored_event_pending = False
            return value

    def _discover_front_camera(self) -> str:
        if shutil.which("termux-camera-info") is None:
            return ""

        try:
            result = subprocess.run(
                ["termux-camera-info"],
                capture_output=True,
                text=True,
                timeout=6.0,
                check=False,
            )
            if result.returncode != 0:
                return ""

            payload = json.loads(result.stdout)
            for item in payload:
                if str(item.get("facing", "")).lower() == "front":
                    return str(item.get("id", ""))
        except Exception:
            return ""

        return ""

    def _capture(self, camera_id: str) -> bool:
        if shutil.which("termux-camera-photo") is None:
            return False

        try:
            self.capture_path.unlink(missing_ok=True)
        except OSError:
            pass

        try:
            result = subprocess.run(
                [
                    "termux-camera-photo",
                    "-c",
                    camera_id,
                    str(self.capture_path),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=8.0,
                check=False,
            )
        except Exception:
            return False

        if result.returncode != 0:
            return False

        try:
            return self.capture_path.exists() and self.capture_path.stat().st_size > 0
        except OSError:
            return False

    def _run(self) -> None:
        if cv2 is None or np is None:
            self._set_error(
                "OpenCV unavailable. Install the Termux opencv-python package."
            )
            return

        camera_id = self._discover_front_camera()
        if not camera_id:
            self._set_error("Front camera unavailable.")
            return

        with self.lock:
            self.state.available = True
            self.state.camera_id = camera_id
            self.state.error = ""

        while not self.stop_event.is_set():
            started = time.monotonic()

            if self._capture(camera_id):
                try:
                    frame = cv2.imread(str(self.capture_path))
                    if frame is not None and frame.size:
                        # Mirror so left/right feels natural to the person
                        # standing in front of the display.
                        frame = cv2.flip(frame, 1)
                        self._analyze(frame)
                except Exception as exc:
                    self._set_error(f"Vision analysis failed: {exc}")
                finally:
                    try:
                        self.capture_path.unlink(missing_ok=True)
                    except OSError:
                        pass

            elapsed = time.monotonic() - started
            self.stop_event.wait(max(0.08, self.interval - elapsed))

    def _set_error(self, message: str) -> None:
        with self.lock:
            self.state.available = False
            self.state.error = message

    def _analyze(self, frame) -> None:
        now = time.monotonic()

        max_width = 480
        height, width = frame.shape[:2]

        if width > max_width:
            scale = max_width / float(width)
            frame = cv2.resize(
                frame,
                (
                    max_width,
                    max(1, int(height * scale)),
                ),
                interpolation=cv2.INTER_AREA,
            )

        height, width = frame.shape[:2]
        face_box = self._detect_face(frame)
        face_present = face_box is not None

        face_x = 0.0
        face_y = 0.0
        face_area = 0.0

        if face_box is not None:
            x, y, w, h = face_box
            center_x = x + w / 2.0
            center_y = y + h / 2.0

            face_x = max(-1.0, min(1.0, center_x / width * 2.0 - 1.0))
            face_y = max(-1.0, min(1.0, center_y / height * 2.0 - 1.0))
            face_area = (w * h) / float(width * height)

            if self.face_first_seen <= 0.0:
                self.face_first_seen = now

            self.last_face_at = now
            self.face_history.append((now, face_x, face_y))
        elif now - self.last_face_at > 2.8:
            # Haar detection can miss a single low-light snapshot. Do not reset
            # the boredom timer because of one bad frame.
            self.face_first_seen = 0.0
            self.face_history.clear()

        stationary_seconds = self._stationary_seconds(now)

        if (
            stationary_seconds >= 24.0
            and now - self.last_bored_event >= 42.0
        ):
            self.last_bored_event = now
            with self.lock:
                self.bored_event_pending = True

        fingers, palm_confidence = self._detect_open_hand(
            frame,
            face_box,
        )

        five_fingers = fingers >= 5 and palm_confidence >= 0.48

        if five_fingers:
            self.five_streak += 1
        else:
            self.five_streak = max(0, self.five_streak - 1)

        if (
            self.five_streak >= 2
            and now - self.last_five_event >= 15.0
        ):
            self.last_five_event = now
            self.five_streak = 0
            with self.lock:
                self.five_event_pending = True

        with self.lock:
            self.state = VisionState(
                available=True,
                camera_id=self.state.camera_id,
                face_present=face_present,
                face_x=face_x,
                face_y=face_y,
                face_area=face_area,
                stationary_seconds=stationary_seconds,
                five_fingers=five_fingers,
                open_palm_confidence=palm_confidence,
                last_frame_at=now,
                error="",
            )

    def _detect_face(self, frame):
        if self.face_detector is None:
            return None

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)

        minimum = max(42, int(min(frame.shape[:2]) * 0.12))

        faces = self.face_detector.detectMultiScale(
            gray,
            scaleFactor=1.12,
            minNeighbors=5,
            minSize=(minimum, minimum),
        )

        if len(faces) == 0:
            return None

        return max(
            faces,
            key=lambda box: int(box[2]) * int(box[3]),
        )

    def _stationary_seconds(self, now: float) -> float:
        if len(self.face_history) < 8:
            return 0.0

        recent = [
            item
            for item in self.face_history
            if now - item[0] <= 30.0
        ]

        if len(recent) < 8:
            return 0.0

        xs = [item[1] for item in recent]
        ys = [item[2] for item in recent]

        spread_x = max(xs) - min(xs)
        spread_y = max(ys) - min(ys)

        if spread_x > 0.15 or spread_y > 0.14:
            return 0.0

        return max(0.0, recent[-1][0] - recent[0][0])

    def _detect_open_hand(
        self,
        frame,
        face_box,
    ) -> tuple[int, float]:
        """Heuristic open-palm detector used when MediaPipe is unavailable.

        It intentionally requires a large stable contour and several convexity
        defects. Lighting and background affect it, so the caller also requires
        multiple consecutive detections before triggering an action.
        """

        image = cv2.GaussianBlur(frame, (5, 5), 0)
        ycrcb = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb)

        # Keep luminance above near-black so a dark room/background does not
        # become one giant "skin" contour. Chrominance bounds stay deliberately
        # broad because the phone may see different skin tones and lighting.
        lower = np.array([24, 125, 70], dtype=np.uint8)
        upper = np.array([255, 190, 148], dtype=np.uint8)
        mask = cv2.inRange(ycrcb, lower, upper)

        if face_box is not None:
            x, y, w, h = face_box
            pad = int(max(w, h) * 0.18)
            cv2.rectangle(
                mask,
                (
                    max(0, x - pad),
                    max(0, y - pad),
                ),
                (
                    min(mask.shape[1] - 1, x + w + pad),
                    min(mask.shape[0] - 1, y + h + pad),
                ),
                0,
                -1,
            )

        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(
            mask,
            cv2.MORPH_OPEN,
            kernel,
            iterations=1,
        )
        mask = cv2.morphologyEx(
            mask,
            cv2.MORPH_CLOSE,
            kernel,
            iterations=2,
        )

        contours, _ = cv2.findContours(
            mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )

        if not contours:
            return 0, 0.0

        frame_area = float(mask.shape[0] * mask.shape[1])

        candidates = [
            contour
            for contour in contours
            if 0.035 * frame_area
            <= cv2.contourArea(contour)
            <= 0.62 * frame_area
        ]

        if not candidates:
            return 0, 0.0

        contour = max(
            candidates,
            key=cv2.contourArea,
        )

        contour_area = float(cv2.contourArea(contour))
        hull_points = cv2.convexHull(contour)
        hull_area = float(cv2.contourArea(hull_points))

        if hull_area <= 1.0:
            return 0, 0.0

        solidity = contour_area / hull_area
        if solidity < 0.40 or solidity > 0.94:
            return 0, 0.0

        hull_indices = cv2.convexHull(
            contour,
            returnPoints=False,
        )

        if hull_indices is None or len(hull_indices) < 4:
            return 0, 0.0

        defects = cv2.convexityDefects(
            contour,
            hull_indices,
        )

        if defects is None:
            return 0, 0.0

        x, y, w, h = cv2.boundingRect(contour)
        depth_min = max(7.0, min(w, h) * 0.055)

        valid_defects = 0

        for row in defects[:, 0]:
            start_i, end_i, far_i, depth_raw = map(int, row)

            start = contour[start_i][0].astype(float)
            end = contour[end_i][0].astype(float)
            far = contour[far_i][0].astype(float)

            a = float(np.linalg.norm(end - start))
            b = float(np.linalg.norm(far - start))
            c = float(np.linalg.norm(end - far))

            if b <= 1e-6 or c <= 1e-6:
                continue

            cosine = clamp_scalar(
                (b * b + c * c - a * a)
                / (2.0 * b * c),
                -1.0,
                1.0,
            )
            angle = math.degrees(math.acos(cosine))
            depth = depth_raw / 256.0

            if angle <= 95.0 and depth >= depth_min:
                valid_defects += 1

        fingers = max(0, min(5, valid_defects + 1))

        relative_area = contour_area / frame_area
        confidence = min(
            1.0,
            relative_area * 5.0
            + valid_defects * 0.12
            + max(0.0, 0.88 - solidity) * 0.45,
        )

        # Four valleys usually means five extended fingers. A clean four-finger
        # valley pattern is promoted to five rather than requiring a fragile
        # fifth contour tip.
        if valid_defects >= 4:
            fingers = 5
        elif (
            valid_defects >= 3
            and h >= w * 0.82
            and relative_area >= 0.045
            and solidity <= 0.88
        ):
            # Phone snapshots often merge two neighboring fingertips after
            # blur/morphology, leaving only three visible valleys. In that
            # specific open-palm geometry, treat it as five fingers, but only
            # after the multi-frame stability gate in _analyze().
            fingers = 5

        return fingers, confidence


def clamp_scalar(
    value: float,
    low: float,
    high: float,
) -> float:
    return max(low, min(high, value))
