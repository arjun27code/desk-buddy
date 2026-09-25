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
    raise SystemExit(2)


# The face below is an independent Python/Termux:GUI adaptation of the
# public behavior and geometry documented by FluxGarage RoboEyes.
# Reference project: https://github.com/FluxGarage/RoboEyes
VIRTUAL_W = 128.0
VIRTUAL_H = 64.0
FPS = 50.0
FRAME_TIME = 1.0 / FPS
EMOTION_HOLD = 2.5
EMOTION_CYCLE = ["happy", "curious", "annoyed", "sad"]

BLACK = (0, 0, 0, 255)
CYAN = (18, 238, 242, 255)


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

            for index, (x1, y1) in enumerate(pts):
                x2, y2 = pts[(index + 1) % len(pts)]
                if y1 == y2:
                    continue

                low = min(y1, y2)
                high = max(y1, y2)
                if not (low <= scan_y < high):
                    continue

                t = (scan_y - y1) / (y2 - y1)
                intersections.append(x1 + t * (x2 - x1))

            intersections.sort()
            for index in range(0, len(intersections) - 1, 2):
                self.span(
                    yy,
                    int(math.floor(intersections[index])),
                    int(math.ceil(intersections[index + 1])),
                    color,
                )


class VirtualOLED:
    """Maps an exact 128x64 RoboEyes-style coordinate system to the phone."""

    def __init__(self, canvas: PixelCanvas):
        self.canvas = canvas

        # Do not stretch the eyes to the whole phone. A 128x64 OLED is 2:1,
        # so keep that visual window intact and center it on the phone.
        target_w = canvas.width * 0.90
        self.scale = target_w / VIRTUAL_W
        self.ox = (canvas.width - VIRTUAL_W * self.scale) / 2.0
        face_h = VIRTUAL_H * self.scale
        self.oy = canvas.height * 0.47 - face_h / 2.0

    def x(self, value: float) -> float:
        return self.ox + value * self.scale

    def y(self, value: float) -> float:
        return self.oy + value * self.scale

    def s(self, value: float) -> float:
        return value * self.scale

    def rounded_rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        radius: float,
        color: tuple[int, int, int, int],
    ) -> None:
        self.canvas.rounded_rect(
            self.x(x),
            self.y(y),
            self.s(w),
            self.s(h),
            self.s(radius),
            color,
        )

    def polygon(
        self,
        points: Iterable[tuple[float, float]],
        color: tuple[int, int, int, int],
    ) -> None:
        self.canvas.polygon(
            [(self.x(x), self.y(y)) for x, y in points],
            color,
        )

    def phone_to_virtual(self, x: float, y: float) -> tuple[float, float]:
        return (
            (x - self.ox) / self.scale,
            (y - self.oy) / self.scale,
        )


@dataclass
class RoboState:
    # Default RoboEyes geometry.
    eye_l_w_default: float = 36.0
    eye_l_h_default: float = 36.0
    eye_r_w_default: float = 36.0
    eye_r_h_default: float = 36.0
    radius_l_default: float = 8.0
    radius_r_default: float = 8.0
    space_default: float = 10.0

    # Current and next geometry. Eyes intentionally start almost closed.
    eye_l_w: float = 36.0
    eye_l_h: float = 1.0
    eye_r_w: float = 36.0
    eye_r_h: float = 1.0
    eye_l_w_next: float = 36.0
    eye_l_h_next: float = 36.0
    eye_r_w_next: float = 36.0
    eye_r_h_next: float = 36.0

    radius_l: float = 8.0
    radius_r: float = 8.0
    radius_l_next: float = 8.0
    radius_r_next: float = 8.0

    space: float = 10.0
    space_next: float = 10.0

    eye_l_x: float = 23.0
    eye_l_y: float = 14.0
    eye_r_x: float = 69.0
    eye_r_y: float = 14.0
    eye_l_x_next: float = 23.0
    eye_l_y_next: float = 14.0
    eye_r_x_next: float = 69.0
    eye_r_y_next: float = 14.0

    eye_l_h_offset: float = 0.0
    eye_r_h_offset: float = 0.0

    eyelid_tired: float = 0.0
    eyelid_tired_next: float = 0.0
    eyelid_angry: float = 0.0
    eyelid_angry_next: float = 0.0
    happy_bottom: float = 0.0
    happy_bottom_next: float = 0.0

    tired: bool = False
    angry: bool = False
    happy: bool = False
    curious: bool = True

    eye_l_open: bool = False
    eye_r_open: bool = False

    autoblink: bool = True
    blink_interval: int = 3
    blink_variation: int = 2
    next_blink: float = 0.0

    idle: bool = True
    idle_interval: int = 2
    idle_variation: int = 2
    next_idle: float = 0.0

    h_flicker: bool = False
    h_flicker_amp: float = 2.0
    h_flicker_alt: bool = False

    v_flicker: bool = False
    v_flicker_amp: float = 5.0
    v_flicker_alt: bool = False

    laugh: bool = False
    laugh_until: float = 0.0

    mood_name: str = "idle"
    mood_until: float = 0.0
    cycle_index: int = 0

    touch_down_at: float = 0.0
    touch_down_x: float = 0.0
    touch_down_y: float = 0.0
    touch_last_x: float = 0.0
    touch_last_y: float = 0.0
    manual_until: float = 0.0


class RoboEyesFace:
    def __init__(self):
        self.state = RoboState()
        self.lock = threading.Lock()

        now = time.monotonic()
        self.state.next_blink = self._next_blink(now)
        self.state.next_idle = self._next_idle(now)

    @staticmethod
    def _rand_variation(value: int) -> int:
        if value <= 0:
            return 0
        return random.randrange(value)

    def _next_blink(self, now: float) -> float:
        s = self.state
        return now + s.blink_interval + self._rand_variation(s.blink_variation)

    def _next_idle(self, now: float) -> float:
        s = self.state
        return now + s.idle_interval + self._rand_variation(s.idle_variation)

    def _constraint_x(self) -> float:
        s = self.state
        return max(
            0.0,
            VIRTUAL_W - s.eye_l_w - s.space - s.eye_r_w,
        )

    def _constraint_y(self) -> float:
        return max(0.0, VIRTUAL_H - self.state.eye_l_h_default)

    def set_position(self, name: str) -> None:
        s = self.state
        max_x = self._constraint_x()
        max_y = self._constraint_y()

        positions = {
            "N": (max_x / 2.0, 0.0),
            "NE": (max_x, 0.0),
            "E": (max_x, max_y / 2.0),
            "SE": (max_x, max_y),
            "S": (max_x / 2.0, max_y),
            "SW": (0.0, max_y),
            "W": (0.0, max_y / 2.0),
            "NW": (0.0, 0.0),
            "DEFAULT": (max_x / 2.0, max_y / 2.0),
        }

        s.eye_l_x_next, s.eye_l_y_next = positions.get(
            name,
            positions["DEFAULT"],
        )

    def set_mood(self, mood: str) -> None:
        s = self.state
        s.tired = mood == "tired"
        s.angry = mood == "angry"
        s.happy = mood == "happy"

    def close(self) -> None:
        s = self.state
        s.eye_l_h_next = 1.0
        s.eye_r_h_next = 1.0
        s.eye_l_open = False
        s.eye_r_open = False

    def open(self) -> None:
        s = self.state
        s.eye_l_open = True
        s.eye_r_open = True

    def blink(self) -> None:
        self.close()
        self.open()

    def set_emotion(self, mood: str) -> None:
        s = self.state
        now = time.monotonic()

        # Clear behavior left by previous emotion.
        s.h_flicker = False
        s.v_flicker = False
        s.laugh = False

        s.mood_name = mood
        if mood == "idle":
            s.mood_until = 0.0
            self.set_mood("default")
            self.set_position("DEFAULT")
            s.idle = True
            s.curious = True
            return

        s.mood_until = now + EMOTION_HOLD

        if mood == "happy":
            self.set_mood("happy")
            s.idle = False
            s.curious = True
            s.laugh = True
            s.laugh_until = now + 0.5

        elif mood == "curious":
            self.set_mood("default")
            s.curious = True
            self.set_position("NE")
            s.idle = False

        elif mood == "annoyed":
            self.set_mood("angry")
            s.idle = False
            s.curious = True
            s.h_flicker = True
            s.h_flicker_amp = 2.0

        elif mood == "sad":
            self.set_mood("tired")
            self.set_position("S")
            s.idle = False
            s.curious = True

    def cycle_emotion(self) -> None:
        s = self.state
        mood = EMOTION_CYCLE[s.cycle_index]
        s.cycle_index = (s.cycle_index + 1) % len(EMOTION_CYCLE)
        self.set_emotion(mood)

    def on_touch(
        self,
        action: str,
        x: float,
        y: float,
        oled: VirtualOLED,
    ) -> None:
        s = self.state
        now = time.monotonic()
        vx, vy = oled.phone_to_virtual(x, y)

        if action == "down":
            s.touch_down_at = now
            s.touch_down_x = x
            s.touch_down_y = y
            s.touch_last_x = x
            s.touch_last_y = y

        if action in {"down", "move"}:
            max_x = self._constraint_x()
            max_y = self._constraint_y()

            # The finger controls the complete pair, just like setPosition().
            normalized_x = max(0.0, min(1.0, vx / VIRTUAL_W))
            normalized_y = max(0.0, min(1.0, vy / VIRTUAL_H))

            s.eye_l_x_next = normalized_x * max_x
            s.eye_l_y_next = normalized_y * max_y
            s.manual_until = now + 0.8
            s.idle = False

            s.touch_last_x = x
            s.touch_last_y = y

        if action == "up":
            duration = now - s.touch_down_at
            distance = math.hypot(
                s.touch_last_x - s.touch_down_x,
                s.touch_last_y - s.touch_down_y,
            )

            if duration <= 0.35 and distance <= 28.0:
                self.cycle_emotion()
            elif s.mood_name == "idle":
                s.idle = True
                s.next_idle = self._next_idle(now)

    def _update_curiosity(self) -> None:
        s = self.state
        if not s.curious:
            s.eye_l_h_offset = 0.0
            s.eye_r_h_offset = 0.0
            return

        max_x = self._constraint_x()

        s.eye_l_h_offset = 8.0 if s.eye_l_x_next <= 10.0 else 0.0

        right_next = s.eye_l_x_next + s.eye_l_w + s.space
        right_edge_threshold = VIRTUAL_W - s.eye_r_w - 10.0
        s.eye_r_h_offset = 8.0 if right_next >= right_edge_threshold else 0.0

        # max_x is intentionally read above because the original curiosity
        # behavior is tied to the same screen constraints used by positions.
        _ = max_x

    def update(self, now: float) -> None:
        s = self.state

        if s.mood_name != "idle" and now >= s.mood_until:
            self.set_emotion("idle")

        if s.manual_until and now >= s.manual_until:
            s.manual_until = 0.0
            if s.mood_name == "idle":
                s.idle = True
                s.next_idle = self._next_idle(now)

        if s.autoblink and now >= s.next_blink:
            self.blink()
            s.next_blink = self._next_blink(now)

        if s.idle and s.manual_until == 0.0 and now >= s.next_idle:
            max_x = max(1, int(self._constraint_x()))
            max_y = max(1, int(self._constraint_y()))
            s.eye_l_x_next = float(random.randrange(max_x))
            s.eye_l_y_next = float(random.randrange(max_y))
            s.next_idle = self._next_idle(now)

        if s.laugh:
            if now < s.laugh_until:
                s.v_flicker = True
                s.v_flicker_amp = 5.0
            else:
                s.v_flicker = False
                s.laugh = False

        self._update_curiosity()

        # Smooth transitions copied conceptually from RoboEyes:
        # current = (current + next) / 2.
        s.eye_l_h = (s.eye_l_h + s.eye_l_h_next + s.eye_l_h_offset) / 2.0
        s.eye_l_y += (s.eye_l_h_default - s.eye_l_h) / 2.0
        s.eye_l_y -= s.eye_l_h_offset / 2.0

        s.eye_r_h = (s.eye_r_h + s.eye_r_h_next + s.eye_r_h_offset) / 2.0
        s.eye_r_y += (s.eye_r_h_default - s.eye_r_h) / 2.0
        s.eye_r_y -= s.eye_r_h_offset / 2.0

        if s.eye_l_open and s.eye_l_h <= 1.0 + s.eye_l_h_offset:
            s.eye_l_h_next = s.eye_l_h_default

        if s.eye_r_open and s.eye_r_h <= 1.0 + s.eye_r_h_offset:
            s.eye_r_h_next = s.eye_r_h_default

        s.eye_l_w = (s.eye_l_w + s.eye_l_w_next) / 2.0
        s.eye_r_w = (s.eye_r_w + s.eye_r_w_next) / 2.0
        s.space = (s.space + s.space_next) / 2.0

        s.eye_l_x = (s.eye_l_x + s.eye_l_x_next) / 2.0
        s.eye_l_y = (s.eye_l_y + s.eye_l_y_next) / 2.0

        s.eye_r_x_next = s.eye_l_x_next + s.eye_l_w + s.space
        s.eye_r_y_next = s.eye_l_y_next
        s.eye_r_x = (s.eye_r_x + s.eye_r_x_next) / 2.0
        s.eye_r_y = (s.eye_r_y + s.eye_r_y_next) / 2.0

        s.radius_l = (s.radius_l + s.radius_l_next) / 2.0
        s.radius_r = (s.radius_r + s.radius_r_next) / 2.0

        if s.tired:
            s.eyelid_tired_next = s.eye_l_h / 2.0
            s.eyelid_angry_next = 0.0
        else:
            s.eyelid_tired_next = 0.0

        if s.angry:
            s.eyelid_angry_next = s.eye_l_h / 2.0
            s.eyelid_tired_next = 0.0
        else:
            s.eyelid_angry_next = 0.0

        s.happy_bottom_next = s.eye_l_h / 2.0 if s.happy else 0.0

        s.eyelid_tired = (s.eyelid_tired + s.eyelid_tired_next) / 2.0
        s.eyelid_angry = (s.eyelid_angry + s.eyelid_angry_next) / 2.0
        s.happy_bottom = (s.happy_bottom + s.happy_bottom_next) / 2.0

    def draw(self, canvas: PixelCanvas, oled: VirtualOLED, now: float) -> None:
        s = self.state
        self.update(now)
        canvas.clear()

        lx = s.eye_l_x
        ly = s.eye_l_y
        rx = s.eye_r_x
        ry = s.eye_r_y

        if s.h_flicker:
            dx = s.h_flicker_amp if s.h_flicker_alt else -s.h_flicker_amp
            s.h_flicker_alt = not s.h_flicker_alt
            lx += dx
            rx += dx

        if s.v_flicker:
            dy = s.v_flicker_amp if s.v_flicker_alt else -s.v_flicker_amp
            s.v_flicker_alt = not s.v_flicker_alt
            ly += dy
            ry += dy

        # Base eyes. No pupils, no highlights, no glow.
        oled.rounded_rect(
            lx,
            ly,
            s.eye_l_w,
            s.eye_l_h,
            s.radius_l,
            CYAN,
        )
        oled.rounded_rect(
            rx,
            ry,
            s.eye_r_w,
            s.eye_r_h,
            s.radius_r,
            CYAN,
        )

        # TIRED top eyelids.
        if s.eyelid_tired > 0.05:
            oled.polygon(
                [
                    (lx, ly - 1),
                    (lx + s.eye_l_w, ly - 1),
                    (lx, ly + s.eyelid_tired - 1),
                ],
                BLACK,
            )
            oled.polygon(
                [
                    (rx, ry - 1),
                    (rx + s.eye_r_w, ry - 1),
                    (rx + s.eye_r_w, ry + s.eyelid_tired - 1),
                ],
                BLACK,
            )

        # ANGRY top eyelids.
        if s.eyelid_angry > 0.05:
            oled.polygon(
                [
                    (lx, ly - 1),
                    (lx + s.eye_l_w, ly - 1),
                    (lx + s.eye_l_w, ly + s.eyelid_angry - 1),
                ],
                BLACK,
            )
            oled.polygon(
                [
                    (rx, ry - 1),
                    (rx + s.eye_r_w, ry - 1),
                    (rx, ry + s.eyelid_angry - 1),
                ],
                BLACK,
            )

        # HAPPY bottom eyelids. This is intentionally a black rounded rectangle
        # overlay, matching the RoboEyes drawing method instead of inventing
        # curved pupils or a separate smile.
        if s.happy_bottom > 0.05:
            oled.rounded_rect(
                lx - 1,
                (ly + s.eye_l_h) - s.happy_bottom + 1,
                s.eye_l_w + 2,
                s.eye_l_h_default,
                s.radius_l,
                BLACK,
            )
            oled.rounded_rect(
                rx - 1,
                (ry + s.eye_r_h) - s.happy_bottom + 1,
                s.eye_r_w + 2,
                s.eye_r_h_default,
                s.radius_r,
                BLACK,
            )


def choose_buffer_size(screen_w_px: int, screen_h_px: int) -> tuple[int, int]:
    if screen_w_px <= 0 or screen_h_px <= 0:
        return 400, 900

    max_w = 400
    scale = min(1.0, max_w / float(screen_w_px))
    width = max(320, int(round(screen_w_px * scale)))
    height = max(620, int(round(screen_h_px * scale)))

    if height > 920:
        factor = 920.0 / height
        width = max(300, int(round(width * factor)))
        height = 920

    return width, height


def event_worker(
    connection,
    image_view,
    face: RoboEyesFace,
    oled: VirtualOLED,
    stop: threading.Event,
) -> None:
    try:
        for event in connection.events():
            if stop.is_set():
                return

            if event.type == tg.Event.destroy and event.value.get("finishing", False):
                stop.set()
                return

            if event.type != tg.Event.touch:
                continue

            if event.value.get("id") != image_view.id:
                continue

            action = event.value.get("action", "")
            pointer_groups = event.value.get("pointers") or []
            if not pointer_groups:
                continue

            latest = pointer_groups[-1]
            if not latest:
                continue

            pointer = latest[0]
            try:
                x = float(pointer["x"])
                y = float(pointer["y"])
            except (KeyError, TypeError, ValueError):
                continue

            with face.lock:
                face.on_touch(action, x, y, oled)

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
                0xFF00FFFF,
            )

            image = tg.ImageView(activity)
            image.setdimensions(tg.View.MATCH_PARENT, tg.View.MATCH_PARENT)
            image.setbackgroundcolor(0xFF000000)
            image.sendtouchevent(True)

            dims = [0, 0]
            for _ in range(200):
                dims = image.getdimensions()
                if dims and dims[0] > 0 and dims[1] > 0:
                    break
                time.sleep(0.01)

            if not dims or dims[0] <= 0 or dims[1] <= 0:
                dims = [1080, 2400]

            buffer_w, buffer_h = choose_buffer_size(int(dims[0]), int(dims[1]))
            buffer = tg.Buffer(connection, buffer_w, buffer_h)
            image.setbuffer(buffer)

            face = RoboEyesFace()
            stop = threading.Event()

            with buffer as mem:
                canvas = PixelCanvas(mem, buffer_w, buffer_h)
                oled = VirtualOLED(canvas)

                watcher = threading.Thread(
                    target=event_worker,
                    args=(connection, image, face, oled, stop),
                    daemon=True,
                )
                watcher.start()

                next_frame = time.monotonic()

                while not stop.is_set():
                    now = time.monotonic()

                    with face.lock:
                        face.draw(canvas, oled, now)

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
        print("Desk Buddy could not connect to Termux:GUI.")
        print("Make sure Termux and Termux:GUI are installed from the same source.")
        print(f"Details: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
