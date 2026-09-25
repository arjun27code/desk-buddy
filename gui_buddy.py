#!/usr/bin/env python3
from __future__ import annotations

import math
import random
import sys
import threading
import time
from dataclasses import dataclass
from typing import Iterable

try:
    import termuxgui as tg
except ModuleNotFoundError:
    print("Termux:GUI Python bindings are missing.")
    print("Run: python -m pip install termuxgui")
    sys.exit(2)


FPS = 40.0
FRAME_TIME = 1.0 / FPS
EMOTION_HOLD = 2.5
EMOTION_CYCLE = ["happy", "curious", "annoyed", "sad"]

BLACK = (0, 0, 0, 255)
CYAN = (24, 232, 238, 255)
CYAN_GLOW = (0, 58, 64, 255)
CYAN_GLOW_2 = (0, 25, 29, 255)
WHITE = (240, 255, 255, 255)


@dataclass
class FaceState:
    mood: str = "idle"
    mood_until: float = 0.0
    cycle_index: int = 0

    gaze_x: float = 0.0
    gaze_y: float = 0.0
    target_x: float = 0.0
    target_y: float = 0.0
    next_gaze: float = 0.0
    manual_gaze_until: float = 0.0

    blinking: bool = False
    blink_started: float = 0.0
    blink_duration: float = 0.20
    next_blink: float = 0.0
    double_blink_pending: bool = False

    touch_down_time: float = 0.0
    touch_down_x: float = 0.0
    touch_down_y: float = 0.0
    touch_last_x: float = 0.0
    touch_last_y: float = 0.0


class PixelCanvas:
    def __init__(self, mem, width: int, height: int):
        self.mem = mem
        self.width = width
        self.height = height
        self.pitch = width * 4
        self._black = bytes(BLACK) * (width * height)

    def clear(self) -> None:
        self.mem[:] = self._black

    @staticmethod
    def _px(color: tuple[int, int, int, int]) -> bytes:
        return bytes(color)

    def span(
        self,
        y: int,
        x1: int,
        x2: int,
        color: tuple[int, int, int, int],
    ) -> None:
        if y < 0 or y >= self.height:
            return

        x1 = max(0, int(x1))
        x2 = min(self.width, int(x2))
        if x2 <= x1:
            return

        start = y * self.pitch + x1 * 4
        end = y * self.pitch + x2 * 4
        self.mem[start:end] = self._px(color) * (x2 - x1)

    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        color: tuple[int, int, int, int],
    ) -> None:
        x1 = int(round(x))
        y1 = int(round(y))
        x2 = int(round(x + w))
        y2 = int(round(y + h))
        for yy in range(y1, y2):
            self.span(yy, x1, x2, color)

    def rounded_rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        radius: float,
        color: tuple[int, int, int, int],
    ) -> None:
        if w <= 0 or h <= 0:
            return

        x = int(round(x))
        y = int(round(y))
        w = max(1, int(round(w)))
        h = max(1, int(round(h)))
        radius = max(0, min(int(round(radius)), w // 2, h // 2))

        if radius <= 1:
            self.rect(x, y, w, h, color)
            return

        r = float(radius)
        for row in range(h):
            if row < radius:
                dy = r - row - 0.5
                inside = max(0.0, r * r - dy * dy)
                inset = int(math.ceil(r - math.sqrt(inside)))
            elif row >= h - radius:
                dy = row - (h - radius) + 0.5
                inside = max(0.0, r * r - dy * dy)
                inset = int(math.ceil(r - math.sqrt(inside)))
            else:
                inset = 0

            self.span(y + row, x + inset, x + w - inset, color)

    def ellipse(
        self,
        cx: float,
        cy: float,
        rx: float,
        ry: float,
        color: tuple[int, int, int, int],
    ) -> None:
        if rx <= 0 or ry <= 0:
            return

        top = int(math.floor(cy - ry))
        bottom = int(math.ceil(cy + ry))

        for yy in range(top, bottom + 1):
            normalized = (yy + 0.5 - cy) / ry
            if abs(normalized) > 1.0:
                continue
            half = rx * math.sqrt(max(0.0, 1.0 - normalized * normalized))
            self.span(yy, int(cx - half), int(cx + half) + 1, color)

    def polygon(
        self,
        points: Iterable[tuple[float, float]],
        color: tuple[int, int, int, int],
    ) -> None:
        pts = [(float(x), float(y)) for x, y in points]
        if len(pts) < 3:
            return

        min_y = int(math.floor(min(y for _, y in pts)))
        max_y = int(math.ceil(max(y for _, y in pts)))

        for yy in range(min_y, max_y + 1):
            scan_y = yy + 0.5
            intersections: list[float] = []

            for i, (x1, y1) in enumerate(pts):
                x2, y2 = pts[(i + 1) % len(pts)]
                if y1 == y2:
                    continue

                low_y = min(y1, y2)
                high_y = max(y1, y2)
                if not (low_y <= scan_y < high_y):
                    continue

                t = (scan_y - y1) / (y2 - y1)
                intersections.append(x1 + t * (x2 - x1))

            intersections.sort()
            for i in range(0, len(intersections) - 1, 2):
                self.span(
                    yy,
                    int(math.floor(intersections[i])),
                    int(math.ceil(intersections[i + 1])),
                    color,
                )


class RoboFace:
    def __init__(self, width: int, height: int):
        self.w = width
        self.h = height

        now = time.monotonic()
        self.state = FaceState(
            next_gaze=now + random.uniform(0.8, 1.8),
            next_blink=now + random.uniform(1.8, 4.0),
        )
        self.lock = threading.Lock()

    def set_mood(self, mood: str) -> None:
        now = time.monotonic()
        self.state.mood = mood
        self.state.mood_until = now + EMOTION_HOLD

        if mood == "curious":
            self.state.target_x = 0.78
            self.state.target_y = -0.72
        elif mood == "sad":
            self.state.target_x = 0.0
            self.state.target_y = 0.72
        elif mood == "annoyed":
            self.state.target_x = -0.15
            self.state.target_y = 0.0
        elif mood == "happy":
            self.state.target_x = 0.0
            self.state.target_y = -0.08

    def cycle_emotion(self) -> None:
        mood = EMOTION_CYCLE[self.state.cycle_index]
        self.state.cycle_index = (self.state.cycle_index + 1) % len(EMOTION_CYCLE)
        self.set_mood(mood)

    def _start_blink(self, now: float) -> None:
        self.state.blinking = True
        self.state.blink_started = now
        self.state.blink_duration = random.uniform(0.16, 0.22)
        self.state.double_blink_pending = random.random() < 0.10
        self.state.next_blink = now + random.uniform(2.0, 5.0)

    def _blink_open(self, now: float) -> float:
        s = self.state
        if not s.blinking:
            return 1.0

        p = (now - s.blink_started) / max(0.05, s.blink_duration)
        if p >= 1.0:
            s.blinking = False
            if s.double_blink_pending:
                s.double_blink_pending = False
                s.next_blink = now + 0.13
            return 1.0

        if p < 0.5:
            eased = 1.0 - (p / 0.5)
        else:
            eased = (p - 0.5) / 0.5

        return max(0.04, eased * eased * (3.0 - 2.0 * eased))

    def update(self, now: float) -> None:
        s = self.state

        if s.mood != "idle" and now >= s.mood_until:
            s.mood = "idle"
            s.next_gaze = now + random.uniform(0.4, 1.2)

        if not s.blinking and now >= s.next_blink:
            self._start_blink(now)

        if now >= s.manual_gaze_until:
            if s.mood == "curious":
                s.target_x = 0.78
                s.target_y = -0.72
            elif s.mood == "sad":
                s.target_x = 0.0
                s.target_y = 0.72
            elif s.mood == "annoyed":
                s.target_x = -0.10
                s.target_y = 0.0
            elif s.mood == "happy":
                s.target_x = 0.0
                s.target_y = -0.10
            elif now >= s.next_gaze and not s.blinking:
                s.target_x, s.target_y = random.choice(
                    [
                        (0.0, 0.0),
                        (0.0, 0.0),
                        (0.0, 0.0),
                        (-0.75, 0.0),
                        (0.75, 0.0),
                        (-0.58, -0.50),
                        (0.58, -0.50),
                        (-0.45, 0.48),
                        (0.45, 0.48),
                    ]
                )
                s.next_gaze = now + random.uniform(0.5, 3.0)

        ease = 0.16 if s.mood == "idle" else 0.25
        s.gaze_x += (s.target_x - s.gaze_x) * ease
        s.gaze_y += (s.target_y - s.gaze_y) * ease

    def on_touch(
        self,
        action: str,
        x: float,
        y: float,
    ) -> None:
        now = time.monotonic()
        s = self.state

        if action == "down":
            s.touch_down_time = now
            s.touch_down_x = x
            s.touch_down_y = y
            s.touch_last_x = x
            s.touch_last_y = y

        if action in {"down", "move"}:
            nx = (x / max(1, self.w) - 0.5) * 2.0
            ny = (y / max(1, self.h) - 0.5) * 2.0
            s.target_x = max(-1.0, min(1.0, nx))
            s.target_y = max(-1.0, min(1.0, ny))
            s.manual_gaze_until = now + 0.85
            s.touch_last_x = x
            s.touch_last_y = y

        if action == "up":
            duration = now - s.touch_down_time
            travel = math.hypot(
                s.touch_last_x - s.touch_down_x,
                s.touch_last_y - s.touch_down_y,
            )
            if duration <= 0.35 and travel <= max(25.0, self.w * 0.06):
                self.cycle_emotion()

    def _face_geometry(self, now: float):
        s = self.state

        face_w = self.w * 0.86
        scale = face_w / 128.0
        face_h = 64.0 * scale

        center_x = self.w / 2.0
        center_y = self.h * 0.48

        eye_w = 36.0 * scale
        eye_h = 34.0 * scale
        radius = 8.0 * scale
        space = 12.0 * scale

        if s.mood == "happy":
            eye_h *= 0.88
        elif s.mood == "sad":
            eye_h *= 0.82
        elif s.mood == "annoyed":
            eye_h *= 0.86

        shift_x = s.gaze_x * 9.0 * scale
        shift_y = s.gaze_y * 6.5 * scale

        if s.mood == "happy":
            shift_y += math.sin(now * 16.0) * 2.1 * scale
        elif s.mood == "annoyed":
            shift_x += math.sin(now * 30.0) * 1.8 * scale

        blink = self._blink_open(now)
        eye_h *= blink

        left_x = center_x - space / 2.0 - eye_w + shift_x
        right_x = center_x + space / 2.0 + shift_x
        base_y = center_y - eye_h / 2.0 + shift_y

        left_h = eye_h
        right_h = eye_h
        left_y = base_y
        right_y = base_y

        if s.mood == "curious":
            extra = 7.0 * scale
            if s.gaze_x >= 0:
                right_h += extra
                right_y -= extra / 2.0
            else:
                left_h += extra
                left_y -= extra / 2.0

        return (
            left_x,
            left_y,
            eye_w,
            left_h,
            right_x,
            right_y,
            eye_w,
            right_h,
            radius,
            scale,
        )

    def _draw_eye(
        self,
        canvas: PixelCanvas,
        x: float,
        y: float,
        w: float,
        h: float,
        radius: float,
        side: str,
        mood: str,
        scale: float,
    ) -> None:
        if h <= 2.0:
            canvas.rounded_rect(
                x,
                y + h / 2.0,
                w,
                max(2.0, 1.8 * scale),
                1.0 * scale,
                CYAN,
            )
            return

        glow_pad = 4.5 * scale
        canvas.rounded_rect(
            x - glow_pad * 2,
            y - glow_pad * 2,
            w + glow_pad * 4,
            h + glow_pad * 4,
            radius + glow_pad * 2,
            CYAN_GLOW_2,
        )
        canvas.rounded_rect(
            x - glow_pad,
            y - glow_pad,
            w + glow_pad * 2,
            h + glow_pad * 2,
            radius + glow_pad,
            CYAN_GLOW,
        )
        canvas.rounded_rect(x, y, w, h, radius, CYAN)

        if mood == "happy":
            canvas.ellipse(
                x + w / 2.0,
                y + h * 1.03,
                w * 0.60,
                h * 0.62,
                BLACK,
            )

        elif mood == "annoyed":
            cut = h * 0.42
            if side == "left":
                canvas.polygon(
                    [
                        (x - 1, y - 1),
                        (x + w + 1, y - 1),
                        (x + w + 1, y + cut),
                        (x - 1, y + cut * 0.08),
                    ],
                    BLACK,
                )
            else:
                canvas.polygon(
                    [
                        (x - 1, y - 1),
                        (x + w + 1, y - 1),
                        (x + w + 1, y + cut * 0.08),
                        (x - 1, y + cut),
                    ],
                    BLACK,
                )

        elif mood == "sad":
            cut = h * 0.34
            if side == "left":
                canvas.polygon(
                    [
                        (x - 1, y - 1),
                        (x + w + 1, y - 1),
                        (x + w + 1, y + cut * 0.06),
                        (x - 1, y + cut),
                    ],
                    BLACK,
                )
            else:
                canvas.polygon(
                    [
                        (x - 1, y - 1),
                        (x + w + 1, y - 1),
                        (x + w + 1, y + cut),
                        (x - 1, y + cut * 0.06),
                    ],
                    BLACK,
                )

    def draw(self, canvas: PixelCanvas, now: float) -> None:
        self.update(now)
        canvas.clear()

        (
            lx,
            ly,
            lw,
            lh,
            rx,
            ry,
            rw,
            rh,
            radius,
            scale,
        ) = self._face_geometry(now)

        mood = self.state.mood
        self._draw_eye(canvas, lx, ly, lw, lh, radius, "left", mood, scale)
        self._draw_eye(canvas, rx, ry, rw, rh, radius, "right", mood, scale)


def choose_buffer_size(screen_w_px: int, screen_h_px: int) -> tuple[int, int]:
    if screen_w_px <= 0 or screen_h_px <= 0:
        return 432, 960

    max_w = 432
    scale = min(1.0, max_w / float(screen_w_px))
    width = max(320, int(round(screen_w_px * scale)))
    height = max(560, int(round(screen_h_px * scale)))

    if height > 980:
        factor = 980.0 / height
        width = max(300, int(round(width * factor)))
        height = 980

    return width, height


def event_worker(
    connection,
    image_view,
    face: RoboFace,
    stop: threading.Event,
) -> None:
    try:
        for event in connection.events():
            if stop.is_set():
                return

            if event.type == tg.Event.destroy:
                if event.value.get("finishing", False):
                    stop.set()
                    return

            if event.type != tg.Event.touch:
                continue

            if event.value.get("id") != image_view.id:
                continue

            action = event.value.get("action", "")
            groups = event.value.get("pointers") or []
            if not groups:
                continue

            latest = groups[-1]
            if not latest:
                continue

            pointer = latest[0]
            try:
                x = float(pointer["x"])
                y = float(pointer["y"])
            except (KeyError, TypeError, ValueError):
                continue

            with face.lock:
                face.on_touch(action, x, y)

    except Exception:
        stop.set()


def main() -> int:
    try:
        with tg.Connection() as connection:
            activity = tg.Activity(connection)
            activity.setorientation("portrait")
            activity.keepscreenon(True)
            activity.settheme(
                0xFF000000,
                0xFF000000,
                0xFF000000,
                0xFFFFFFFF,
                0xFFFFFF00,
            )

            image = tg.ImageView(activity)
            image.setdimensions(tg.View.MATCH_PARENT, tg.View.MATCH_PARENT)
            image.setbackgroundcolor(0xFF000000)
            image.sendtouchevent(True)

            for _ in range(200):
                dims = image.getdimensions()
                if dims and dims[0] > 0 and dims[1] > 0:
                    break
                time.sleep(0.01)
            else:
                dims = [1080, 2400]

            buffer_w, buffer_h = choose_buffer_size(int(dims[0]), int(dims[1]))
            buffer = tg.Buffer(connection, buffer_w, buffer_h)
            image.setbuffer(buffer)

            face = RoboFace(buffer_w, buffer_h)
            stop = threading.Event()

            watcher = threading.Thread(
                target=event_worker,
                args=(connection, image, face, stop),
                daemon=True,
            )
            watcher.start()

            with buffer as mem:
                canvas = PixelCanvas(mem, buffer_w, buffer_h)
                next_frame = time.monotonic()

                while not stop.is_set():
                    now = time.monotonic()

                    with face.lock:
                        face.draw(canvas, now)

                    buffer.blit()
                    image.refresh()

                    next_frame += FRAME_TIME
                    delay = next_frame - time.monotonic()

                    if delay > 0:
                        time.sleep(delay)
                    else:
                        next_frame = time.monotonic()

            return 0

    except RuntimeError as exc:
        print()
        print("Desk Buddy native renderer could not connect to Termux:GUI.")
        print("Install the Termux:GUI Android plugin from the SAME source as Termux.")
        print("Then run: python -m pip install termuxgui")
        print()
        print(f"Details: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
