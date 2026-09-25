#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import random
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Iterable

from buddy_advanced import (
    BuddyVoice,
    SceneEngine,
    SensorFusion,
    discover_sensor_request,
    time_label,
)
from doodle_show import DoodleShow
from game_hub import GameHub
from oled_asset_show import OledAssetShow

try:
    import termuxgui as tg
except ModuleNotFoundError:
    print("Termux:GUI Python bindings are missing.")
    print("Run: python -m pip install termuxgui")
    raise SystemExit(2)


VIRTUAL_W = 128.0
VIRTUAL_H = 64.0
# Termux:GUI's shared-buffer refresh is much happier around 30 FPS than 50
# FPS on a phone. RoboEyes interpolation still looks smooth while pixel traffic
# and refresh pressure drop substantially.
FPS = 30.0
FRAME_TIME = 1.0 / FPS

# The uploaded OLED animation uses 64 ms frame holds. We keep the native
# renderer smooth, but quantize a tiny expression/wobble layer to this cadence
# to get the hand-animated pose-to-pose feel without copying its frames.
HAND_ANIM_STEP = 0.064
POSE_ENTRY_SECONDS = 1.20

EMOTION_HOLD = 5.5
DIZZY_HOLD = 6.0
EMOTION_CYCLE = [
    "happy",
    "curious",
    "annoyed",
    "sad",
    "surprised",
    "sleepy",
    "love",
    "excited",
    "shy",
    "confused",
    "scared",
    "proud",
    "bored",
]

EMOTION_LINES = {
    "happy": ["I feel good today.", "This is a good moment.", "Okay, I am happy."],
    "curious": ["What is that?", "I need to inspect this.", "Something caught my eye."],
    "annoyed": ["I am mildly annoyed.", "That was unnecessary.", "My patience is tiny."],
    "sad": ["I feel a little sad.", "Rain fits the mood.", "I need a quiet minute."],
    "surprised": ["Wait. What?", "I did not expect that.", "Attention acquired."],
    "sleepy": ["I am getting sleepy.", "Nap calculations started.", "My eyes are heavy."],
    "love": ["You are acceptable company.", "Friend detected.", "This is nice."],
    "excited": ["This is exciting!", "Energy level maximum.", "I am very awake now."],
    "shy": ["Do not stare.", "I am being shy.", "This is slightly embarrassing."],
    "confused": ["I am confused.", "That does not compute yet.", "Give me a second."],
    "scared": ["That startled me.", "I am a little scared.", "Please stop doing that."],
    "proud": ["I did that well.", "Tiny robot, respectable performance.", "I am proud of that."],
    "bored": ["I am bored.", "Nothing is happening.", "Entertainment levels are low."],
    "dizzy": ["Everything is spinning.", "Too much motion.", "I am dizzy."],
}

AUTO_EMOTION_POOL = [
    "happy",
    "happy",
    "curious",
    "curious",
    "sleepy",
    "love",
    "excited",
    "shy",
    "confused",
    "proud",
    "bored",
    "surprised",
    "sad",
    "annoyed",
    "scared",
]

BLACK = (0, 0, 0, 255)
CYAN = (18, 238, 242, 255)
CYAN_DIM = (7, 100, 106, 255)
BLUE = (20, 90, 210, 255)
WHITE = (240, 255, 255, 255)
YELLOW = (255, 214, 70, 255)
MAGENTA = (255, 65, 175, 255)
RED = (255, 70, 70, 255)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def smoothstep(value: float) -> float:
    x = clamp(value, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def ease_out_back(value: float, overshoot: float = 1.70158) -> float:
    x = clamp(value, 0.0, 1.0) - 1.0
    return 1.0 + (overshoot + 1.0) * x * x * x + overshoot * x * x


def stepped_time(value: float, step: float = HAND_ANIM_STEP) -> float:
    if value <= 0.0:
        return 0.0
    return math.floor(value / step) * step


def dim_color(
    color: tuple[int, int, int, int],
    strength: float,
) -> tuple[int, int, int, int]:
    s = clamp(strength, 0.0, 1.0)
    return (
        int(color[0] * s),
        int(color[1] * s),
        int(color[2] * s),
        255,
    )


class PixelCanvas:
    def __init__(self, mem, width: int, height: int):
        self.mem = mem
        self.width = width
        self.height = height
        self.pitch = width * 4
        self._black = bytes(BLACK) * (width * height)

    def clear(self) -> None:
        self.mem[:] = self._black

    def blend_rgba(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        rgba: bytes,
        alpha: float = 0.40,
    ) -> None:
        """Alpha-blend a small RGBA image into the native pixel buffer."""

        if (
            width <= 0
            or height <= 0
            or not rgba
        ):
            return

        x = int(x)
        y = int(y)
        alpha = clamp(alpha, 0.0, 1.0)

        dst_x1 = max(0, x)
        dst_y1 = max(0, y)
        dst_x2 = min(self.width, x + width)
        dst_y2 = min(self.height, y + height)

        if dst_x2 <= dst_x1 or dst_y2 <= dst_y1:
            return

        src_x1 = dst_x1 - x
        src_y1 = dst_y1 - y
        src_x2 = src_x1 + (dst_x2 - dst_x1)
        src_y2 = src_y1 + (dst_y2 - dst_y1)

        if np is not None:
            try:
                src = np.frombuffer(
                    rgba,
                    dtype=np.uint8,
                ).reshape(
                    height,
                    width,
                    4,
                )

                dst = np.frombuffer(
                    self.mem,
                    dtype=np.uint8,
                ).reshape(
                    self.height,
                    self.width,
                    4,
                )

                src_region = src[
                    src_y1:src_y2,
                    src_x1:src_x2,
                    :3,
                ].astype(
                    np.float32,
                )

                dst_region = dst[
                    dst_y1:dst_y2,
                    dst_x1:dst_x2,
                    :3,
                ].astype(
                    np.float32,
                )

                blended = (
                    dst_region * (1.0 - alpha)
                    + src_region * alpha
                )

                dst[
                    dst_y1:dst_y2,
                    dst_x1:dst_x2,
                    :3,
                ] = blended.astype(
                    np.uint8,
                )
                dst[
                    dst_y1:dst_y2,
                    dst_x1:dst_x2,
                    3,
                ] = 255
                return

            except Exception:
                pass

        # Small pure-Python fallback if numpy cannot expose the Termux buffer.
        source = memoryview(rgba)
        destination = self.mem

        for row in range(
            dst_y2 - dst_y1
        ):
            source_y = src_y1 + row
            destination_y = dst_y1 + row

            for column in range(
                dst_x2 - dst_x1
            ):
                source_x = src_x1 + column
                destination_x = dst_x1 + column

                source_offset = (
                    source_y * width
                    + source_x
                ) * 4

                destination_offset = (
                    destination_y * self.width
                    + destination_x
                ) * 4

                for channel in range(3):
                    old = destination[
                        destination_offset
                        + channel
                    ]
                    new = source[
                        source_offset
                        + channel
                    ]

                    destination[
                        destination_offset
                        + channel
                    ] = int(
                        old * (1.0 - alpha)
                        + new * alpha
                    )

                destination[
                    destination_offset + 3
                ] = 255

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

    def circle(
        self,
        cx: float,
        cy: float,
        radius: float,
        color: tuple[int, int, int, int],
    ) -> None:
        if radius <= 0:
            return

        top = int(math.floor(cy - radius))
        bottom = int(math.ceil(cy + radius))

        for yy in range(top, bottom + 1):
            dy = yy + 0.5 - cy
            inside = radius * radius - dy * dy
            if inside < 0:
                continue

            half = math.sqrt(inside)
            self.span(
                yy,
                int(math.floor(cx - half)),
                int(math.ceil(cx + half)) + 1,
                color,
            )

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        color: tuple[int, int, int, int],
        thickness: int = 1,
    ) -> None:
        x1_i = int(round(x1))
        y1_i = int(round(y1))
        x2_i = int(round(x2))
        y2_i = int(round(y2))

        dx = abs(x2_i - x1_i)
        dy = -abs(y2_i - y1_i)
        sx = 1 if x1_i < x2_i else -1
        sy = 1 if y1_i < y2_i else -1
        err = dx + dy

        x = x1_i
        y = y1_i

        while True:
            half = max(0, thickness // 2)
            for yy in range(y - half, y + half + 1):
                self.span(yy, x - half, x + half + 1, color)

            if x == x2_i and y == y2_i:
                break

            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy

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
    def __init__(self, canvas: PixelCanvas):
        self.canvas = canvas
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

    def circle(
        self,
        x: float,
        y: float,
        radius: float,
        color: tuple[int, int, int, int],
    ) -> None:
        self.canvas.circle(
            self.x(x),
            self.y(y),
            self.s(radius),
            color,
        )

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        color: tuple[int, int, int, int],
        thickness: float = 1.0,
    ) -> None:
        self.canvas.line(
            self.x(x1),
            self.y(y1),
            self.x(x2),
            self.y(y2),
            color,
            max(1, int(round(self.s(thickness)))),
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
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    ttl: float
    size: float
    color: tuple[int, int, int, int]


class EmotionEffects:
    def __init__(self):
        self.rockets: list[Particle] = []
        self.fireworks: list[Particle] = []
        self.confetti: list[Particle] = []
        self.rain: list[Particle] = []
        self.hearts: list[Particle] = []
        self.sleepy_marks: list[Particle] = []

        self.last_firework = 0.0
        self.last_confetti = 0.0
        self.last_mood = "idle"
        self.rain_mode = "medium"
        self.next_rain_change = 0.0
        self.last_heart = 0.0
        self.last_sleepy = 0.0

        self.intensity = {
            name: 0.0
            for name in [
                "happy",
                "curious",
                "annoyed",
                "sad",
                "surprised",
                "sleepy",
                "love",
                "excited",
                "dizzy",
                "shy",
                "confused",
                "scared",
                "proud",
                "bored",
            ]
        }

        self.sparkles = [
            (
                random.uniform(5, 123),
                random.uniform(4, 60),
                random.uniform(0, math.tau),
            )
            for _ in range(14)
        ]

    def _approach_intensity(self, mood: str, dt: float) -> None:
        for name in self.intensity:
            target = 1.0 if mood == name else 0.0
            speed = 4.0 if target > self.intensity[name] else 2.4
            delta = speed * dt

            if self.intensity[name] < target:
                self.intensity[name] = min(target, self.intensity[name] + delta)
            else:
                self.intensity[name] = max(target, self.intensity[name] - delta)

    def _spawn_firework(self) -> None:
        # Proper sky-rocket: launch from below, travel upward, then burst.
        self.rockets.append(
            Particle(
                x=random.uniform(14, 114),
                y=random.uniform(66, 74),
                vx=random.uniform(-2.4, 2.4),
                vy=random.uniform(-48.0, -36.0),
                life=0.0,
                ttl=random.uniform(0.72, 1.05),
                size=random.uniform(0.8, 1.25),
                color=random.choice(
                    [CYAN, WHITE, YELLOW, MAGENTA, BLUE, RED]
                ),
            )
        )

    def _explode_firework(self, rocket: Particle) -> None:
        spokes = random.choice([16, 18, 22, 26])
        phase = random.uniform(0.0, math.tau)

        for index in range(spokes):
            angle = phase + math.tau * index / spokes + random.uniform(-0.08, 0.08)
            speed = random.uniform(13.0, 29.0)
            color = random.choice(
                [rocket.color, CYAN, WHITE, YELLOW, MAGENTA, BLUE, RED]
            )
            self.fireworks.append(
                Particle(
                    x=rocket.x,
                    y=rocket.y,
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed,
                    life=0.0,
                    ttl=random.uniform(0.75, 1.35),
                    size=random.uniform(0.45, 1.15),
                    color=color,
                )
            )

    def _update_rockets(self, dt: float) -> None:
        active: list[Particle] = []

        for rocket in self.rockets:
            rocket.life += dt
            rocket.x += rocket.vx * dt
            rocket.y += rocket.vy * dt
            rocket.vy += 5.5 * dt

            if rocket.life >= rocket.ttl:
                self._explode_firework(rocket)
            else:
                active.append(rocket)

        self.rockets[:] = active

    def _spawn_confetti(self) -> None:
        for _ in range(9):
            self.confetti.append(
                Particle(
                    x=random.uniform(5, 123),
                    y=-2,
                    vx=random.uniform(-5, 5),
                    vy=random.uniform(12, 22),
                    life=0.0,
                    ttl=random.uniform(1.4, 2.4),
                    size=random.uniform(0.8, 1.6),
                    color=random.choice([CYAN, YELLOW, MAGENTA, WHITE]),
                )
            )

    def _spawn_heart(self) -> None:
        self.hearts.append(
            Particle(
                x=random.uniform(10, 118),
                y=65,
                vx=random.uniform(-2.5, 2.5),
                vy=random.uniform(-9, -15),
                life=0.0,
                ttl=random.uniform(2.5, 4.0),
                size=random.uniform(1.4, 2.5),
                color=random.choice([MAGENTA, CYAN, WHITE]),
            )
        )

    def _spawn_sleepy(self) -> None:
        self.sleepy_marks.append(
            Particle(
                x=random.uniform(83, 112),
                y=random.uniform(26, 48),
                vx=random.uniform(0.5, 1.8),
                vy=random.uniform(-3.5, -6.0),
                life=0.0,
                ttl=random.uniform(2.0, 3.2),
                size=random.uniform(1.2, 1.8),
                color=CYAN_DIM,
            )
        )

    def _ensure_rain(
        self,
        eye_color: tuple[int, int, int, int],
    ) -> None:
        profiles = {
            "slow": (16, (13.0, 22.0), 0.46, (3.0, 5.0)),
            "medium": (28, (23.0, 38.0), 0.40, (4.0, 7.0)),
            "fast": (44, (38.0, 61.0), 0.34, (6.0, 10.0)),
        }
        target_count, speed_range, darkness, length_range = profiles[self.rain_mode]
        rain_color = dim_color(eye_color, darkness)

        while len(self.rain) < target_count:
            length = random.uniform(*length_range)
            self.rain.append(
                Particle(
                    x=random.uniform(0, 128),
                    y=random.uniform(-25, 64),
                    vx=random.uniform(-4.2, -1.0),
                    vy=random.uniform(*speed_range),
                    life=length,
                    ttl=9999,
                    size=random.uniform(0.45, 1.05),
                    color=rain_color,
                )
            )

        if len(self.rain) > target_count:
            del self.rain[target_count:]

    def _draw_heart(
        self,
        oled: VirtualOLED,
        x: float,
        y: float,
        size: float,
        color: tuple[int, int, int, int],
    ) -> None:
        points = [
            (x, y + size * 0.9),
            (x - size * 1.1, y - size * 0.15),
            (x - size * 0.95, y - size * 0.75),
            (x - size * 0.45, y - size),
            (x, y - size * 0.55),
            (x + size * 0.45, y - size),
            (x + size * 0.95, y - size * 0.75),
            (x + size * 1.1, y - size * 0.15),
        ]
        oled.polygon(points, color)

    def _draw_z(
        self,
        oled: VirtualOLED,
        x: float,
        y: float,
        size: float,
        color: tuple[int, int, int, int],
    ) -> None:
        oled.line(x, y, x + size, y, color, 0.7)
        oled.line(x + size, y, x, y + size, color, 0.7)
        oled.line(x, y + size, x + size, y + size, color, 0.7)

    def _update_particles(
        self,
        particles: list[Particle],
        dt: float,
        gravity: float = 0.0,
    ) -> None:
        alive = []

        for p in particles:
            p.life += dt
            if p.life >= p.ttl:
                continue

            p.vy += gravity * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            alive.append(p)

        particles[:] = alive

    def update_and_draw(
        self,
        oled: VirtualOLED,
        mood: str,
        now: float,
        dt: float,
        eye_color: tuple[int, int, int, int] = CYAN,
    ) -> None:
        if mood != self.last_mood:
            if mood == "sad":
                self.rain_mode = random.choice(["slow", "medium", "fast"])
                self.next_rain_change = now + random.uniform(1.5, 2.8)
                self.rain.clear()
            self.last_mood = mood

        if mood == "sad" and now >= self.next_rain_change:
            self.rain_mode = random.choice(["slow", "medium", "fast"])
            self.next_rain_change = now + random.uniform(1.4, 2.6)
            self.rain.clear()

        self._approach_intensity(mood, dt)

        happy_i = self.intensity["happy"]
        sad_i = self.intensity["sad"]
        curious_i = self.intensity["curious"]
        annoyed_i = self.intensity["annoyed"]
        surprised_i = self.intensity["surprised"]
        sleepy_i = self.intensity["sleepy"]
        love_i = self.intensity["love"]
        excited_i = self.intensity["excited"]
        dizzy_i = self.intensity["dizzy"]
        shy_i = self.intensity["shy"]
        confused_i = self.intensity["confused"]
        scared_i = self.intensity["scared"]
        proud_i = self.intensity["proud"]
        bored_i = self.intensity["bored"]

        # Full-screen happy rockets are rendered by SceneEngine.
        if False and happy_i > 0.05 and now - self.last_firework >= 0.62:
            self._spawn_firework()
            self.last_firework = now

        if excited_i > 0.05 and now - self.last_confetti >= 0.30:
            self._spawn_confetti()
            self.last_confetti = now

        if love_i > 0.05 and now - self.last_heart >= 0.32:
            self._spawn_heart()
            self.last_heart = now

        if sleepy_i > 0.05 and now - self.last_sleepy >= 0.75:
            self._spawn_sleepy()
            self.last_sleepy = now

        # Full-screen sad rain is rendered by SceneEngine.
        if False and sad_i > 0.05:
            self._ensure_rain(eye_color)

        self._update_rockets(dt)
        self._update_particles(self.fireworks, dt, gravity=12.0)
        self._update_particles(self.confetti, dt, gravity=8.0)
        self._update_particles(self.hearts, dt, gravity=-0.4)
        self._update_particles(self.sleepy_marks, dt, gravity=-0.2)

        for rocket in self.rockets:
            fade = max(happy_i, 0.22)
            trail_color = dim_color(rocket.color, fade * 0.65)
            oled.line(
                rocket.x,
                rocket.y + 1.5,
                rocket.x - rocket.vx * 0.05,
                rocket.y + 8.0,
                trail_color,
                max(0.65, rocket.size * 0.75),
            )
            oled.circle(
                rocket.x,
                rocket.y,
                max(0.65, rocket.size),
                dim_color(rocket.color, fade),
            )

        for p in self.fireworks:
            fade = (1.0 - p.life / p.ttl) * max(happy_i, 0.25)
            oled.line(
                p.x - p.vx * 0.025,
                p.y - p.vy * 0.025,
                p.x,
                p.y,
                dim_color(p.color, fade),
                p.size,
            )

        if sad_i > 0.01:
            for p in self.rain:
                p.x += p.vx * dt
                p.y += p.vy * dt

                if p.y > 72:
                    p.y = random.uniform(-18, -2)
                    p.x = random.uniform(0, 128)

                if p.x < -4:
                    p.x = 132

                drop_length = max(3.0, p.life)
                oled.line(
                    p.x,
                    p.y,
                    p.x - drop_length * 0.28,
                    p.y + drop_length,
                    dim_color(p.color, 0.90 * sad_i),
                    p.size,
                )

        if curious_i > 0.01:
            for index, (x, y, phase) in enumerate(self.sparkles):
                pulse = 0.5 + 0.5 * math.sin(now * 4.2 + phase + index)
                strength = curious_i * (0.18 + 0.62 * pulse)
                oled.circle(
                    x,
                    y,
                    0.55 + pulse * 0.55,
                    dim_color(CYAN, strength),
                )

        if annoyed_i > 0.01:
            jitter = math.sin(now * 24.0) * 1.2
            color = dim_color(RED, 0.75 * annoyed_i)

            for y in (19, 27, 35, 43):
                oled.line(2, y + jitter, 15, y + jitter, color, 0.8)
                oled.line(113, y - jitter, 126, y - jitter, color, 0.8)

        if surprised_i > 0.01:
            color = dim_color(WHITE, 0.55 * surprised_i)

            for index in range(10):
                angle = now * 0.8 + math.tau * index / 10.0
                r1 = 44.0
                r2 = 51.0 + math.sin(now * 5.0 + index) * 2.0

                oled.line(
                    64 + math.cos(angle) * r1,
                    32 + math.sin(angle) * r1 * 0.55,
                    64 + math.cos(angle) * r2,
                    32 + math.sin(angle) * r2 * 0.55,
                    color,
                    0.65,
                )

        for p in self.sleepy_marks:
            fade = (1.0 - p.life / p.ttl) * max(sleepy_i, 0.20)
            self._draw_z(
                oled,
                p.x,
                p.y,
                p.size * 3.0,
                dim_color(CYAN, fade * 0.65),
            )

        for p in self.hearts:
            fade = (1.0 - p.life / p.ttl) * max(love_i, 0.25)
            self._draw_heart(
                oled,
                p.x,
                p.y,
                p.size,
                dim_color(p.color, fade),
            )

        for p in self.confetti:
            fade = (1.0 - p.life / p.ttl) * max(excited_i, 0.20)
            oled.line(
                p.x,
                p.y,
                p.x + p.vx * 0.09,
                p.y + 2.5,
                dim_color(p.color, fade),
                p.size,
            )

        if shy_i > 0.01:
            blush = dim_color(MAGENTA, 0.38 * shy_i)
            for x in (18, 110):
                oled.circle(x, 45, 1.4, blush)
                oled.circle(x + (2 if x < 64 else -2), 46.5, 0.8, blush)

        if confused_i > 0.01:
            q = dim_color(YELLOW, 0.65 * confused_i)
            for offset in (0.0, 11.0):
                x = 100 + offset
                oled.line(x, 13, x + 3, 10, q, 0.75)
                oled.line(x + 3, 10, x + 6, 12, q, 0.75)
                oled.line(x + 6, 12, x + 3, 16, q, 0.75)
                oled.line(x + 3, 16, x + 3, 19, q, 0.75)
                oled.circle(x + 3, 22, 0.8, q)

        if scared_i > 0.01:
            sweat = dim_color(BLUE, 0.70 * scared_i)
            for x, phase in ((20, 0.0), (108, 1.2)):
                y = 18 + math.sin(now * 4.0 + phase) * 2.0
                oled.line(x, y, x - 1.2, y + 5.5, sweat, 0.9)
                oled.circle(x - 1.2, y + 6.0, 1.0, sweat)

        if proud_i > 0.01:
            star = dim_color(YELLOW, 0.65 * proud_i)
            for index in range(4):
                angle = now * 0.45 + math.tau * index / 4.0
                x = 64 + math.cos(angle) * 48
                y = 31 + math.sin(angle) * 22
                oled.line(x - 2, y, x + 2, y, star, 0.7)
                oled.line(x, y - 2, x, y + 2, star, 0.7)

        if bored_i > 0.01:
            dots = dim_color(CYAN, 0.42 * bored_i)
            for index in range(3):
                oled.circle(56 + index * 8, 56, 1.1, dots)

        if dizzy_i > 0.01:
            for index in range(8):
                angle = now * 3.0 + math.tau * index / 8.0
                radius = 45.0 + 4.0 * math.sin(now * 2.0 + index)
                x = 64 + math.cos(angle) * radius
                y = 32 + math.sin(angle) * radius * 0.45
                color = [YELLOW, WHITE, MAGENTA, CYAN][index % 4]

                oled.circle(
                    x,
                    y,
                    1.0 + (index % 2) * 0.45,
                    dim_color(color, 0.65 * dizzy_i),
                )


@dataclass
class RoboState:
    eye_l_w_default: float = 36.0
    eye_l_h_default: float = 36.0
    eye_r_w_default: float = 36.0
    eye_r_h_default: float = 36.0
    radius_l_default: float = 8.0
    radius_r_default: float = 8.0
    space_default: float = 10.0

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
    mood_started: float = 0.0
    mood_until: float = 0.0
    transition_duration: float = 0.7
    cycle_index: int = 0

    tilt_target_x: float = 0.0
    tilt_target_y: float = 0.0
    tilt_x: float = 0.0
    tilt_y: float = 0.0

    dizzy_started: float = 0.0

    next_auto_emotion: float = 0.0
    next_sleep: float = 0.0
    sleeping: bool = False
    sleep_started: float = 0.0
    next_wave: float = 0.0
    wave_started: float = 0.0
    wave_until: float = 0.0
    wave_side: int = 1

    last_tap_at: float = 0.0
    tap_streak: int = 0

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
        self.effects = EmotionEffects()
        self.voice = BuddyVoice()
        self.scenes = SceneEngine(self.voice)
        self.last_draw = time.monotonic()

        now = time.monotonic()
        self.state.next_blink = self._next_blink(now)
        self.state.next_idle = self._next_idle(now)
        self.state.next_auto_emotion = now + random.uniform(6.0, 14.0)
        self.state.next_sleep = now + random.uniform(65.0, 125.0)
        self.state.next_wave = now + random.uniform(12.0, 26.0)

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
        return max(0.0, VIRTUAL_W - s.eye_l_w - s.space - s.eye_r_w)

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
        s.tired = mood in {"tired", "sleepy", "bored", "shy"}
        s.angry = mood in {"angry", "annoyed"}
        s.happy = mood in {"happy", "excited", "proud", "love"}

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

    def _reset_geometry_targets(self) -> None:
        s = self.state
        s.eye_l_w_next = s.eye_l_w_default
        s.eye_r_w_next = s.eye_r_w_default
        s.eye_l_h_next = s.eye_l_h_default
        s.eye_r_h_next = s.eye_r_h_default
        s.radius_l_next = s.radius_l_default
        s.radius_r_next = s.radius_r_default
        s.space_next = s.space_default

    def _transition_progress(self, now: float) -> float:
        s = self.state
        if s.mood_started <= 0:
            return 1.0

        return smoothstep(
            (now - s.mood_started) / max(0.05, s.transition_duration)
        )

    def set_emotion(self, mood: str, hold: float | None = None) -> None:
        s = self.state
        now = time.monotonic()

        self._reset_geometry_targets()

        s.h_flicker = False
        s.v_flicker = False
        s.laugh = False

        s.mood_name = mood
        s.mood_started = now

        if mood in EMOTION_LINES and random.random() < 0.72:
            self.voice.say(random.choice(EMOTION_LINES[mood]))

        transition_map = {
            "idle": 0.85,
            "happy": 0.65,
            "curious": 0.90,
            "annoyed": 0.55,
            "sad": 1.05,
            "surprised": 0.40,
            "sleepy": 1.25,
            "love": 0.70,
            "excited": 0.45,
            "dizzy": 0.30,
            "shy": 1.00,
            "confused": 0.85,
            "scared": 0.38,
            "proud": 0.80,
            "bored": 1.30,
        }
        s.transition_duration = transition_map.get(mood, 0.7) * random.uniform(
            0.88,
            1.14,
        )

        if mood == "idle":
            s.mood_until = 0.0
            self.set_mood("default")
            self.set_position("DEFAULT")
            s.idle = True
            s.curious = True
            s.next_auto_emotion = now + random.uniform(7.0, 17.0)
            return

        if hold is not None:
            active_hold = hold
        else:
            active_hold = random.uniform(
                max(4.6, EMOTION_HOLD - 0.8),
                EMOTION_HOLD + 2.4,
            )
        s.mood_until = now + active_hold

        if mood == "happy":
            self.set_mood("happy")
            s.idle = False
            s.curious = True
            s.laugh = True
            s.laugh_until = now + 0.8

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

        elif mood == "surprised":
            self.set_mood("default")
            self.set_position("DEFAULT")
            s.idle = False
            s.curious = False
            s.eye_l_w_next = 28.0
            s.eye_r_w_next = 28.0
            s.eye_l_h_next = 44.0
            s.eye_r_h_next = 44.0
            s.radius_l_next = 12.0
            s.radius_r_next = 12.0
            s.space_next = 14.0

        elif mood == "sleepy":
            self.set_mood("sleepy")
            self.set_position("S")
            s.idle = False
            s.curious = False
            s.eye_l_h_next = 24.0
            s.eye_r_h_next = 24.0

        elif mood == "love":
            self.set_mood("default")
            self.set_position("DEFAULT")
            s.idle = False
            s.curious = False
            s.eye_l_w_next = 34.0
            s.eye_r_w_next = 34.0
            s.eye_l_h_next = 34.0
            s.eye_r_h_next = 34.0
            s.space_next = 14.0

        elif mood == "excited":
            self.set_mood("excited")
            self.set_position("DEFAULT")
            s.idle = False
            s.curious = True
            s.v_flicker = True
            s.v_flicker_amp = 3.0
            s.eye_l_h_next = 40.0
            s.eye_r_h_next = 40.0

        elif mood == "dizzy":
            self.set_mood("default")
            s.idle = False
            s.curious = False
            s.dizzy_started = now
            s.eye_l_w_next = 32.0
            s.eye_r_w_next = 32.0
            s.eye_l_h_next = 32.0
            s.eye_r_h_next = 32.0
            s.space_next = 16.0

        elif mood == "shy":
            self.set_mood("shy")
            self.set_position("SW")
            s.idle = False
            s.curious = False
            s.eye_l_h_next = 28.0
            s.eye_r_h_next = 28.0
            s.eye_l_w_next = 34.0
            s.eye_r_w_next = 34.0
            s.space_next = 13.0

        elif mood == "confused":
            self.set_mood("default")
            self.set_position("NE")
            s.idle = False
            s.curious = True
            s.eye_l_h_next = 38.0
            s.eye_r_h_next = 27.0
            s.eye_l_w_next = 34.0
            s.eye_r_w_next = 37.0
            s.radius_l_next = 9.0
            s.radius_r_next = 6.0
            s.space_next = 12.0

        elif mood == "scared":
            self.set_mood("default")
            self.set_position("DEFAULT")
            s.idle = False
            s.curious = False
            s.eye_l_w_next = 27.0
            s.eye_r_w_next = 27.0
            s.eye_l_h_next = 46.0
            s.eye_r_h_next = 46.0
            s.radius_l_next = 13.0
            s.radius_r_next = 13.0
            s.space_next = 18.0

        elif mood == "proud":
            self.set_mood("proud")
            self.set_position("N")
            s.idle = False
            s.curious = False
            s.eye_l_w_next = 38.0
            s.eye_r_w_next = 38.0
            s.eye_l_h_next = 30.0
            s.eye_r_h_next = 30.0
            s.space_next = 10.0

        elif mood == "bored":
            self.set_mood("bored")
            self.set_position("E")
            s.idle = False
            s.curious = False
            s.eye_l_w_next = 38.0
            s.eye_r_w_next = 38.0
            s.eye_l_h_next = 21.0
            s.eye_r_h_next = 21.0
            s.space_next = 11.0

    def go_to_sleep(self) -> None:
        s = self.state
        now = time.monotonic()
        if s.sleeping:
            return
        s.sleeping = True
        s.sleep_started = now
        s.mood_name = "sleep"
        s.mood_until = 0.0
        s.idle = False
        s.h_flicker = False
        s.v_flicker = False
        s.laugh = False
        s.eye_l_h_next = 1.0
        s.eye_r_h_next = 1.0
        s.eye_l_open = False
        s.eye_r_open = False
        self.voice.say("Good night. Shake me when you need me.", force=True)

    def wake_up(self) -> None:
        s = self.state
        if not s.sleeping:
            return
        s.sleeping = False
        s.eye_l_open = True
        s.eye_r_open = True
        s.eye_l_h_next = s.eye_l_h_default
        s.eye_r_h_next = s.eye_r_h_default
        s.next_sleep = time.monotonic() + random.uniform(85.0, 170.0)
        self.set_emotion("surprised", 2.0)
        self.voice.say("I am awake!", force=True, pitch=1.26, rate=1.08)

    def handle_shake(self) -> None:
        if self.state.sleeping:
            self.wake_up()
        else:
            self.trigger_dizzy()

    def trigger_dizzy(self) -> None:
        if self.state.sleeping or self.state.mood_name == "dizzy":
            return
        self.set_emotion("dizzy", DIZZY_HOLD)

    def trigger_wave(self) -> None:
        s = self.state
        now = time.monotonic()
        s.wave_side = random.choice([-1, 1])
        s.wave_started = now
        s.wave_until = now + random.uniform(2.4, 3.4)
        s.next_wave = s.wave_until + random.uniform(15.0, 32.0)
        s.idle = False

        max_x = self._constraint_x()
        max_y = self._constraint_y()
        s.eye_l_x_next = max_x if s.wave_side > 0 else 0.0
        s.eye_l_y_next = max_y * 0.58

    def cycle_emotion(self) -> None:
        s = self.state
        mood = EMOTION_CYCLE[s.cycle_index]
        s.cycle_index = (s.cycle_index + 1) % len(EMOTION_CYCLE)
        self.set_emotion(mood)

    def set_sensor_tilt(self, tilt_x: float, tilt_y: float) -> None:
        self.state.tilt_target_x = clamp(tilt_x, -1.0, 1.0)
        self.state.tilt_target_y = clamp(tilt_y, -1.0, 1.0)

    def set_camera_attention(
        self,
        present: bool,
        face_x: float = 0.0,
        face_y: float = 0.0,
    ) -> None:
        s = self.state
        now = time.monotonic()

        s.camera_present = bool(present)

        if not present:
            return

        s.camera_x = clamp(face_x, -1.0, 1.0)
        s.camera_y = clamp(face_y, -1.0, 1.0)
        s.camera_last_seen = now

        if not s.camera_announced:
            self.voice.say(
                "Camera attention online.",
                caption_seconds=2.8,
            )
            s.camera_announced = True

    def camera_bored_reaction(self) -> None:
        s = self.state
        if s.sleeping:
            return

        # Camera boredom is an authored reaction rather than a permanent state.
        if random.random() < 0.55:
            self.set_emotion("annoyed", random.uniform(5.0, 7.5))
            self.voice.say(
                random.choice(
                    [
                        "You have been sitting there for a while.",
                        "We are still sitting here.",
                        "I am getting bored watching this.",
                    ]
                ),
                force=True,
            )
        else:
            self.scenes.force(
                random.choice(["peek", "walk", "park"]),
                random.uniform(7.0, 11.0),
            )

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

        if s.sleeping and action == "down":
            self.wake_up()
            return

        if action == "down":
            s.touch_down_at = now
            s.touch_down_x = x
            s.touch_down_y = y
            s.touch_last_x = x
            s.touch_last_y = y

        if action in {"down", "move"}:
            max_x = self._constraint_x()
            max_y = self._constraint_y()

            normalized_x = clamp(vx / VIRTUAL_W, 0.0, 1.0)
            normalized_y = clamp(vy / VIRTUAL_H, 0.0, 1.0)

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

        s.eye_l_h_offset = 8.0 if s.eye_l_x_next <= 10.0 else 0.0

        right_next = s.eye_l_x_next + s.eye_l_w + s.space
        right_edge_threshold = VIRTUAL_W - s.eye_r_w - 10.0
        s.eye_r_h_offset = 8.0 if right_next >= right_edge_threshold else 0.0

    def update(self, now: float) -> None:
        s = self.state

        if s.sleeping:
            s.eye_l_h_next = 1.0
            s.eye_r_h_next = 1.0
            s.eye_l_open = False
            s.eye_r_open = False
            s.eye_l_h = (s.eye_l_h + 1.0) / 2.0
            s.eye_r_h = (s.eye_r_h + 1.0) / 2.0
            s.eye_l_y += (s.eye_l_h_default - s.eye_l_h) / 2.0
            s.eye_r_y += (s.eye_r_h_default - s.eye_r_h) / 2.0
            s.tilt_x += (s.tilt_target_x - s.tilt_x) * 0.05
            s.tilt_y += (s.tilt_target_y - s.tilt_y) * 0.05
            self.scenes.update(now, allow_random=False, sleeping=True)
            return

        if s.mood_name == "sleepy" and now >= s.mood_until:
            if random.random() < 0.42:
                self.go_to_sleep()
                return
            self.set_emotion("idle")
        elif s.mood_name != "idle" and now >= s.mood_until:
            self.set_emotion("idle")

        if (
            s.mood_name == "idle"
            and s.manual_until == 0.0
            and now >= s.next_sleep
            and now >= s.wave_until
        ):
            self.go_to_sleep()
            return

        self.scenes.update(
            now,
            allow_random=(
                s.mood_name == "idle"
                and s.manual_until == 0.0
                and not s.camera_present
            ),
            sleeping=False,
        )

        if s.camera_present and now - s.camera_last_seen > 2.8:
            s.camera_present = False

        if s.mood_name == "idle" and self.scenes.current:
            if self.scenes.current in {"bike", "car"}:
                self.set_position("DEFAULT")
                s.curious = False
            elif self.scenes.current == "park":
                self.set_position("S")
                s.curious = False
            elif self.scenes.current in {"rainbow", "sunny", "night"}:
                self.set_position("N")
                s.curious = True
            elif self.scenes.current == "peek":
                max_x = self._constraint_x()
                max_y = self._constraint_y()
                s.eye_l_x_next = (
                    max_x
                    if self.scenes.peek_side > 0
                    else 0.0
                )
                s.eye_l_y_next = max_y * 0.46
                s.idle = False
                s.curious = True

        camera_can_drive_gaze = (
            s.camera_present
            and s.mood_name == "idle"
            and not self.scenes.current
            and s.wave_until <= now
            and s.manual_until == 0.0
        )

        if camera_can_drive_gaze:
            max_x = self._constraint_x()
            max_y = self._constraint_y()

            # Mirrored front-camera coordinates feel like eye contact rather
            # than CCTV: person on screen-left makes Buddy look screen-left.
            nx = clamp(
                (s.camera_x + 1.0) / 2.0,
                0.0,
                1.0,
            )
            ny = clamp(
                (s.camera_y + 1.0) / 2.0,
                0.0,
                1.0,
            )

            s.eye_l_x_next = nx * max_x
            s.eye_l_y_next = ny * max_y
            s.idle = False
            s.curious = True

        elif (
            not s.camera_present
            and s.mood_name == "idle"
            and not self.scenes.current
            and s.wave_until <= now
            and s.manual_until == 0.0
        ):
            s.idle = True

        if (
            s.mood_name == "idle"
            and s.manual_until == 0.0
            and now >= s.next_auto_emotion
            and now >= s.wave_until
            and not self.scenes.current
        ):
            self.set_emotion(random.choice(AUTO_EMOTION_POOL))

        if (
            s.mood_name == "idle"
            and s.manual_until == 0.0
            and now >= s.next_wave
            and now >= s.wave_until
            and not self.scenes.current
        ):
            self.trigger_wave()

        if s.wave_until > 0.0 and now >= s.wave_until:
            s.wave_until = 0.0
            if s.mood_name == "idle":
                s.idle = True
                self.set_position("DEFAULT")
                s.next_idle = self._next_idle(now)

        if s.manual_until and now >= s.manual_until:
            s.manual_until = 0.0
            if s.mood_name == "idle":
                s.idle = True
                s.next_idle = self._next_idle(now)

        if s.autoblink and now >= s.next_blink:
            self.blink()
            s.next_blink = self._next_blink(now)

        if (
            s.idle
            and not camera_can_drive_gaze
            and s.manual_until == 0.0
            and now >= s.next_idle
        ):
            max_x = max(1, int(self._constraint_x()))
            max_y = max(1, int(self._constraint_y()))
            s.eye_l_x_next = float(random.randrange(max_x))
            s.eye_l_y_next = float(random.randrange(max_y))
            s.next_idle = self._next_idle(now)

        transition = self._transition_progress(now)

        if s.laugh:
            if now < s.laugh_until:
                s.v_flicker = True
                s.v_flicker_amp = 5.0 * transition
            else:
                s.v_flicker = False
                s.laugh = False

        if s.mood_name == "annoyed":
            s.h_flicker_amp = 2.0 * transition

        if s.mood_name == "excited":
            s.v_flicker_amp = 3.0 * transition

        if s.mood_name == "scared":
            tremble = 1.3 * transition
            s.h_flicker = True
            s.h_flicker_amp = tremble

        if s.mood_name == "confused":
            s.radius_l_next = 10.0 + math.sin(now * 2.2) * 1.2
            s.radius_r_next = 6.0 + math.cos(now * 2.2) * 1.0

        if s.mood_name == "bored":
            max_x = self._constraint_x()
            max_y = self._constraint_y()
            s.eye_l_x_next = max_x
            s.eye_l_y_next = clamp(
                max_y / 2.0 + math.sin(now * 0.7) * 0.35,
                0.0,
                max_y,
            )

        self._update_curiosity()

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

        s.tilt_x += (s.tilt_target_x - s.tilt_x) * 0.10
        s.tilt_y += (s.tilt_target_y - s.tilt_y) * 0.10

    def _hand_drawn_jitter(self, now: float) -> tuple[float, float, float]:
        # A tiny deterministic wobble that changes only at the same cadence as
        # the analysed bitmap sequence. It should feel hand-drawn, not shaky.
        frame = int(now / HAND_ANIM_STEP)
        mood_strength = 0.16 if self.state.mood_name == "idle" else 0.34

        jx = math.sin(frame * 12.9898 + 1.7) * mood_strength
        jy = math.sin(frame * 7.233 + 3.1) * mood_strength * 0.72
        jr = math.sin(frame * 5.117 + 4.8) * mood_strength * 0.42
        return jx, jy, jr

    def _emotion_pose(
        self,
        now: float,
    ) -> tuple[float, float, float, float, float]:
        s = self.state

        if s.mood_name == "idle" or s.mood_started <= 0.0:
            return 0.0, 0.0, 1.0, 1.0, 0.0

        age = max(0.0, now - s.mood_started)
        if age >= POSE_ENTRY_SECONDS:
            return 0.0, 0.0, 1.0, 1.0, 0.0

        # Step only this secondary pose layer. The main geometry continues to
        # interpolate smoothly at the native renderer frame rate.
        stepped_age = stepped_time(age)
        t = clamp(stepped_age / POSE_ENTRY_SECONDS, 0.0, 1.0)

        # Short anticipation, then overshoot and settle.
        anticipation = math.sin(
            clamp(t / 0.17, 0.0, 1.0) * math.pi
        )
        spring = math.sin(t * math.pi * 3.2) * math.exp(-3.2 * t)
        settle = ease_out_back(t)

        dx = 0.0
        dy = 0.0
        sx = 1.0
        sy = 1.0
        gap = 0.0

        if s.mood_name == "happy":
            sx = 1.0 - 0.05 * spring
            sy = 1.0 + 0.16 * spring
            dy = -2.2 * abs(spring)
            gap = -1.4 * spring

        elif s.mood_name == "curious":
            dx = 3.4 * spring
            sx = 1.0 + 0.06 * abs(spring)
            sy = 1.0 + 0.04 * spring
            gap = 1.2 * spring

        elif s.mood_name == "annoyed":
            sx = 1.0 + 0.08 * abs(spring)
            sy = 1.0 - 0.10 * abs(spring)
            dx = 1.2 * spring

        elif s.mood_name == "sad":
            dy = 2.8 * smoothstep(t)
            sy = 1.0 - 0.06 * smoothstep(t)
            sx = 1.0 + 0.02 * smoothstep(t)

        elif s.mood_name == "surprised":
            if t < 0.18:
                squeeze = anticipation
                sx = 1.0 - 0.18 * squeeze
                sy = 1.0 - 0.24 * squeeze
            else:
                pop = math.sin((t - 0.18) * math.pi * 2.3) * math.exp(
                    -2.4 * (t - 0.18)
                )
                sx = 1.0 + 0.13 * pop
                sy = 1.0 + 0.24 * pop
                gap = 2.2 * pop

        elif s.mood_name == "sleepy":
            dy = 1.8 * smoothstep(t)
            sy = 1.0 - 0.11 * smoothstep(t)
            sx = 1.0 + 0.04 * smoothstep(t)

        elif s.mood_name == "love":
            pulse = math.sin(t * math.pi * 2.5) * math.exp(-2.2 * t)
            sx = 1.0 + 0.10 * pulse
            sy = 1.0 + 0.10 * pulse
            gap = 1.5 * pulse

        elif s.mood_name == "excited":
            sx = 1.0 - 0.08 * spring
            sy = 1.0 + 0.20 * spring
            dy = -3.0 * abs(spring)
            gap = -1.8 * spring

        elif s.mood_name == "dizzy":
            dx = math.sin(stepped_age * 15.0) * 1.8 * (1.0 - t)
            dy = math.cos(stepped_age * 12.0) * 1.3 * (1.0 - t)

        elif s.mood_name == "shy":
            dx = -1.8 * smoothstep(t)
            dy = 2.4 * smoothstep(t)
            sx = 1.0 - 0.04 * smoothstep(t)
            sy = 1.0 - 0.08 * smoothstep(t)
            gap = 1.5 * smoothstep(t)

        elif s.mood_name == "confused":
            dx = math.sin(stepped_age * 7.0) * 1.2 * (1.0 - t)
            gap = 1.7 * spring
            sx = 1.0 + 0.04 * spring
            sy = 1.0 - 0.03 * spring

        elif s.mood_name == "scared":
            pulse = math.sin(t * math.pi * 3.0) * math.exp(-2.7 * t)
            sx = 1.0 - 0.08 * pulse
            sy = 1.0 + 0.18 * abs(pulse)
            gap = 2.5 * abs(pulse)

        elif s.mood_name == "proud":
            dy = -1.6 * smoothstep(t)
            sx = 1.0 + 0.05 * spring
            sy = 1.0 - 0.05 * smoothstep(t)
            gap = -0.8 * spring

        elif s.mood_name == "bored":
            dy = 1.5 * smoothstep(t)
            sy = 1.0 - 0.10 * smoothstep(t)
            sx = 1.0 + 0.03 * smoothstep(t)

        # A tiny anticipatory compression makes the pose feel authored instead
        # of simply tweened. Fade it quickly so it does not distort the hold.
        if t < 0.17 and s.mood_name not in {"sad", "sleepy"}:
            sx *= 1.0 + 0.025 * anticipation
            sy *= 1.0 - 0.055 * anticipation

        _ = settle
        return dx, dy, sx, sy, gap

    def _draw_motion_accents(
        self,
        oled: VirtualOLED,
        now: float,
        lx: float,
        ly: float,
        lw: float,
        lh: float,
        rx: float,
        ry: float,
        rw: float,
        rh: float,
    ) -> None:
        s = self.state
        if s.mood_name == "idle" or s.mood_started <= 0.0:
            return

        age = max(0.0, now - s.mood_started)
        if age > 1.35:
            return

        p = 1.0 - smoothstep(age / 1.35)
        if p <= 0.01:
            return

        stepped = stepped_time(age)
        wobble = math.sin(stepped * 18.0) * 0.9
        color = dim_color(CYAN, 0.30 + 0.62 * p)

        if s.mood_name in {"happy", "excited"}:
            for x in (lx, rx + rw):
                direction = -1.0 if x < 64 else 1.0
                oled.line(
                    x + direction * 2.0,
                    min(ly, ry) - 5.0 + wobble,
                    x + direction * 8.0,
                    min(ly, ry) - 10.0 + wobble,
                    color,
                    0.75,
                )
                oled.line(
                    x + direction * 3.0,
                    min(ly, ry) + 2.0,
                    x + direction * 10.0,
                    min(ly, ry) - 1.0,
                    color,
                    0.65,
                )

        elif s.mood_name == "curious":
            edge_x = max(rx + rw, lx + lw)
            oled.line(edge_x + 2, ry - 3, edge_x + 8, ry - 7, color, 0.7)
            oled.line(edge_x + 3, ry + 2, edge_x + 10, ry + 1, color, 0.7)
            oled.line(edge_x + 1, ry + 7, edge_x + 7, ry + 10, color, 0.7)

        elif s.mood_name == "annoyed":
            for side_x, direction in ((lx - 2, -1), (rx + rw + 2, 1)):
                oled.line(
                    side_x,
                    ly + 2 + wobble,
                    side_x + direction * 7,
                    ly - 3 + wobble,
                    dim_color(RED, 0.55 + 0.35 * p),
                    0.8,
                )
                oled.line(
                    side_x,
                    ly + 8 - wobble,
                    side_x + direction * 9,
                    ly + 6 - wobble,
                    dim_color(RED, 0.55 + 0.35 * p),
                    0.8,
                )

        elif s.mood_name == "sad":
            tear_color = dim_color(BLUE, 0.60 + 0.25 * p)
            oled.line(
                lx + lw * 0.72,
                ly + lh + 2,
                lx + lw * 0.72 - 1.0,
                ly + lh + 8 + wobble,
                tear_color,
                0.75,
            )
            oled.line(
                rx + rw * 0.28,
                ry + rh + 2,
                rx + rw * 0.28 + 1.0,
                ry + rh + 7 - wobble,
                tear_color,
                0.75,
            )

        elif s.mood_name == "surprised":
            for side_x, direction in ((lx - 2, -1), (rx + rw + 2, 1)):
                oled.line(
                    side_x,
                    ly + lh * 0.20,
                    side_x + direction * 9,
                    ly + lh * 0.10,
                    dim_color(WHITE, 0.50 + 0.35 * p),
                    0.75,
                )
                oled.line(
                    side_x,
                    ly + lh * 0.65,
                    side_x + direction * 10,
                    ly + lh * 0.72,
                    dim_color(WHITE, 0.50 + 0.35 * p),
                    0.75,
                )

    def _draw_wave_hand(
        self,
        oled: VirtualOLED,
        now: float,
    ) -> None:
        s = self.state
        if s.wave_until <= now or s.wave_started <= 0.0:
            return

        age = now - s.wave_started
        duration = max(0.1, s.wave_until - s.wave_started)
        life = clamp(age / duration, 0.0, 1.0)

        # Fade/scale in and out instead of popping a hand onto the display.
        intro = smoothstep(clamp(life / 0.16, 0.0, 1.0))
        outro = 1.0 - smoothstep(clamp((life - 0.80) / 0.20, 0.0, 1.0))
        strength = min(intro, outro)
        if strength <= 0.01:
            return

        stepped = stepped_time(age)
        wave = math.sin(stepped * 8.8) * 3.2
        bounce = math.sin(stepped * 4.4) * 0.8

        side = 1 if s.wave_side > 0 else -1
        palm_x = 111.0 if side > 0 else 17.0
        palm_y = 47.0 + bounce

        hand_color = dim_color(CYAN, 0.92 * strength)
        soft_color = dim_color(CYAN, 0.45 * strength)

        # Tiny arm from screen edge into the palm.
        edge_x = 128.0 if side > 0 else 0.0
        oled.line(
            edge_x,
            56.0,
            palm_x - side * 2.8,
            palm_y + 3.2,
            soft_color,
            2.0,
        )

        # Palm.
        oled.rounded_rect(
            palm_x - 3.8,
            palm_y - 2.8,
            7.6,
            7.8,
            2.6,
            hand_color,
        )

        # Four fingers. The top endpoints oscillate together, producing a
        # readable wave at OLED scale without turning into a detailed hand icon.
        finger_base_y = palm_y - 2.0
        for index, offset in enumerate((-2.5, -0.8, 0.9, 2.5)):
            finger_wave = wave + (index - 1.5) * 0.45
            start_x = palm_x + offset
            end_x = start_x + side * finger_wave * 0.42
            end_y = palm_y - 7.0 - abs(finger_wave) * 0.18
            oled.line(
                start_x,
                finger_base_y,
                end_x,
                end_y,
                hand_color,
                1.05,
            )
            oled.circle(end_x, end_y, 0.55, hand_color)

        # Thumb.
        oled.line(
            palm_x - side * 3.0,
            palm_y + 0.5,
            palm_x - side * 6.0,
            palm_y - 1.0 + wave * 0.10,
            hand_color,
            1.1,
        )

        # Two tiny motion accents around the hand.
        oled.line(
            palm_x + side * 6.0,
            palm_y - 6.0,
            palm_x + side * (9.0 + wave * 0.12),
            palm_y - 9.0,
            soft_color,
            0.65,
        )
        oled.line(
            palm_x + side * 7.0,
            palm_y - 1.0,
            palm_x + side * (10.0 + wave * 0.10),
            palm_y - 2.5,
            soft_color,
            0.65,
        )

    def _draw_heart_eye(
        self,
        oled: VirtualOLED,
        center_x: float,
        center_y: float,
        size: float,
    ) -> None:
        points = [
            (center_x, center_y + size * 0.9),
            (center_x - size * 1.05, center_y - size * 0.05),
            (center_x - size * 0.9, center_y - size * 0.68),
            (center_x - size * 0.42, center_y - size * 0.95),
            (center_x, center_y - size * 0.50),
            (center_x + size * 0.42, center_y - size * 0.95),
            (center_x + size * 0.9, center_y - size * 0.68),
            (center_x + size * 1.05, center_y - size * 0.05),
        ]
        oled.polygon(points, CYAN)

    def draw(self, canvas: PixelCanvas, oled: VirtualOLED, now: float) -> None:
        s = self.state

        dt = clamp(now - self.last_draw, 0.0, 0.08)
        self.last_draw = now

        self.update(now)
        canvas.clear()

        self.scenes.draw(
            canvas,
            now,
            dt,
            mood=s.mood_name,
            eye_color=CYAN,
            sleeping=s.sleeping,
        )

        if s.sleeping:
            # Sleep is a full scene now: bed, sleeping mini Buddy, moon and Zs.
            # Drawing the large RoboEyes over it would rather defeat the point.
            return

        self.effects.update_and_draw(
            oled,
            s.mood_name,
            now,
            dt,
        )

        lx = s.eye_l_x
        ly = s.eye_l_y
        rx = s.eye_r_x
        ry = s.eye_r_y

        lw = s.eye_l_w
        lh = s.eye_l_h
        rw = s.eye_r_w
        rh = s.eye_r_h
        radius_l = s.radius_l
        radius_r = s.radius_r

        pose_dx, pose_dy, pose_sx, pose_sy, pose_gap = self._emotion_pose(now)

        left_cx = lx + lw / 2.0
        left_cy = ly + lh / 2.0
        right_cx = rx + rw / 2.0
        right_cy = ry + rh / 2.0

        lw *= pose_sx
        lh *= pose_sy
        rw *= pose_sx
        rh *= pose_sy

        lx = left_cx - lw / 2.0 + pose_dx - pose_gap / 2.0
        ly = left_cy - lh / 2.0 + pose_dy
        rx = right_cx - rw / 2.0 + pose_dx + pose_gap / 2.0
        ry = right_cy - rh / 2.0 + pose_dy

        hand_x, hand_y, hand_radius = self._hand_drawn_jitter(now)
        lx += hand_x
        rx -= hand_x * 0.35
        ly += hand_y
        ry -= hand_y * 0.30
        radius_l = max(1.0, radius_l + hand_radius)
        radius_r = max(1.0, radius_r - hand_radius * 0.45)

        if self.scenes.current == "peek" and s.mood_name == "idle":
            # Push the complete pair beyond the virtual OLED edge so part of
            # the face is physically clipped by the phone screen. It reads as
            # Buddy leaning out of the display rather than merely looking left.
            peek_shift = self.scenes.peek_side * 19.0
            lx += peek_shift
            rx += peek_shift
            ly += math.sin(now * 3.0) * 0.8
            ry -= math.sin(now * 3.0) * 0.35

        tilt_shift_x = s.tilt_x * 4.0
        tilt_shift_y = s.tilt_y * 2.5
        roll = s.tilt_x * 3.0

        lx += tilt_shift_x
        rx += tilt_shift_x
        ly += tilt_shift_y + roll
        ry += tilt_shift_y - roll

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

        if s.mood_name == "dizzy":
            elapsed = now - s.dizzy_started
            orbit = math.sin(elapsed * 9.0) * 5.0
            opposite = math.cos(elapsed * 7.5) * 4.0
            lx += orbit
            rx -= orbit
            ly += opposite
            ry -= opposite

        self._draw_motion_accents(
            oled,
            now,
            lx,
            ly,
            lw,
            lh,
            rx,
            ry,
            rw,
            rh,
        )

        if s.mood_name == "love":
            self._draw_heart_eye(
                oled,
                lx + lw / 2.0,
                ly + lh / 2.0,
                12.5,
            )
            self._draw_heart_eye(
                oled,
                rx + rw / 2.0,
                ry + rh / 2.0,
                12.5,
            )
            return

        oled.rounded_rect(
            lx,
            ly,
            lw,
            lh,
            radius_l,
            CYAN,
        )
        oled.rounded_rect(
            rx,
            ry,
            rw,
            rh,
            radius_r,
            CYAN,
        )

        if s.eyelid_tired > 0.05:
            oled.polygon(
                [
                    (lx, ly - 1),
                    (lx + lw, ly - 1),
                    (lx, ly + min(lh / 2.0, s.eyelid_tired) - 1),
                ],
                BLACK,
            )
            oled.polygon(
                [
                    (rx, ry - 1),
                    (rx + rw, ry - 1),
                    (rx + rw, ry + min(rh / 2.0, s.eyelid_tired) - 1),
                ],
                BLACK,
            )

        if s.eyelid_angry > 0.05:
            oled.polygon(
                [
                    (lx, ly - 1),
                    (lx + lw, ly - 1),
                    (lx + lw, ly + min(lh / 2.0, s.eyelid_angry) - 1),
                ],
                BLACK,
            )
            oled.polygon(
                [
                    (rx, ry - 1),
                    (rx + rw, ry - 1),
                    (rx, ry + min(rh / 2.0, s.eyelid_angry) - 1),
                ],
                BLACK,
            )

        if s.happy_bottom > 0.05:
            oled.rounded_rect(
                lx - 1,
                (ly + lh) - min(lh / 2.0, s.happy_bottom) + 1,
                lw + 2,
                s.eye_l_h_default,
                radius_l,
                BLACK,
            )
            oled.rounded_rect(
                rx - 1,
                (ry + rh) - min(rh / 2.0, s.happy_bottom) + 1,
                rw + 2,
                s.eye_r_h_default,
                radius_r,
                BLACK,
            )

        self._draw_wave_hand(oled, now)

        if s.mood_name == "dizzy":
            elapsed = now - s.dizzy_started

            for cx, cy in [
                (lx + lw / 2.0, ly + lh / 2.0),
                (rx + rw / 2.0, ry + rh / 2.0),
            ]:
                angle = elapsed * 5.5
                oled.circle(
                    cx + math.cos(angle) * 4.0,
                    cy + math.sin(angle) * 4.0,
                    3.0,
                    BLACK,
                )
                oled.circle(
                    cx - math.cos(angle) * 4.0,
                    cy - math.sin(angle) * 4.0,
                    1.5,
                    BLACK,
                )


class SensorFeed:
    def __init__(self, face: RoboEyesFace):
        self.face = face
        self.stop_event = threading.Event()
        self.process: subprocess.Popen[str] | None = None
        self.thread: threading.Thread | None = None

        self.fusion = SensorFusion()
        self.sensor_request = discover_sensor_request()
        self.sensor_announced = False

    def available(self) -> bool:
        return shutil.which("termux-sensor") is not None

    def start(self) -> None:
        if not self.available():
            return

        self.thread = threading.Thread(
            target=self._run,
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

        if self.process is not None and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=1.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass

        if shutil.which("termux-sensor") is not None:
            try:
                subprocess.run(
                    ["termux-sensor", "-c"],
                    capture_output=True,
                    text=True,
                    timeout=2.0,
                    check=False,
                )
            except Exception:
                pass

    @staticmethod
    def _values_from_payload(
        payload: dict,
        term: str,
    ) -> tuple[float, float, float] | None:
        term_lower = term.lower()

        for name, info in payload.items():
            if term_lower not in str(name).lower():
                continue

            if not isinstance(info, dict):
                continue

            values = info.get("values")
            if not isinstance(values, list) or len(values) < 3:
                continue

            try:
                return (
                    float(values[0]),
                    float(values[1]),
                    float(values[2]),
                )
            except (TypeError, ValueError):
                continue

        return None

    def _handle_payload(self, payload: dict) -> None:
        accel = self._values_from_payload(payload, "accelerometer")
        gyro = self._values_from_payload(payload, "gyroscope")

        if accel is None:
            accel = self._values_from_payload(payload, "accel")

        if gyro is None:
            gyro = self._values_from_payload(payload, "gyro")

        if accel is None and gyro is None:
            return

        now = time.monotonic()
        tilt_x, tilt_y, shake = self.fusion.update(
            accel=accel,
            gyro=gyro,
            now=now,
        )

        with self.face.lock:
            self.face.set_sensor_tilt(tilt_x, tilt_y)

            if (
                not self.sensor_announced
                and self.fusion.baseline_roll is not None
                and self.fusion.baseline_pitch is not None
            ):
                self.face.voice.say(
                    "Motion sensors online.",
                    caption_seconds=2.8,
                )
                self.sensor_announced = True

            if shake:
                self.face.handle_shake()

    def _run(self) -> None:
        request = self.sensor_request or "Accelerometer,Gyroscope"
        command = [
            "termux-sensor",
            "-s",
            request,
            "-d",
            "50",
        ]

        try:
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except Exception:
            return

        if self.process.stdout is None:
            return

        buffer = ""
        depth = 0

        try:
            for line in self.process.stdout:
                if self.stop_event.is_set():
                    break

                if not line.strip() and not buffer:
                    continue

                buffer += line
                depth += line.count("{") - line.count("}")

                if depth > 0:
                    continue

                text = buffer.strip()
                buffer = ""
                depth = 0

                if not text:
                    continue

                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    continue

                if isinstance(payload, dict):
                    self._handle_payload(payload)

        finally:
            if self.process.poll() is None:
                try:
                    self.process.terminate()
                except Exception:
                    pass


def choose_buffer_size(screen_w_px: int, screen_h_px: int) -> tuple[int, int]:
    if screen_w_px <= 0 or screen_h_px <= 0:
        return 320, 700

    # Rendering at the physical 1080x2400-ish phone resolution would be
    # absurdly expensive in pure Python. 320px wide is still crisp for this
    # stylized UI and cuts the shared-buffer bandwidth by roughly a third.
    max_w = 320
    scale = min(1.0, max_w / float(screen_w_px))
    width = max(280, int(round(screen_w_px * scale)))
    height = max(540, int(round(screen_h_px * scale)))

    if height > 720:
        factor = 720.0 / height
        width = max(270, int(round(width * factor)))
        height = 720

    return width, height


def draw_camera_preview(
    canvas: PixelCanvas,
    vision,
) -> None:
    if (
        not vision.available
        or not vision.preview_rgba
        or vision.preview_width <= 0
        or vision.preview_height <= 0
    ):
        return

    width = int(vision.preview_width)
    height = int(vision.preview_height)

    max_width = max(
        72,
        int(canvas.width * 0.34),
    )

    if width > max_width:
        # CameraVision already produces a small thumbnail, so this should be
        # rare. Skip runtime resampling rather than burning phone CPU.
        return

    margin = max(
        8,
        int(canvas.width * 0.025),
    )

    x = canvas.width - width - margin
    y = margin

    # Subtle frame behind the 40% alpha camera feed.
    canvas.rounded_rect(
        x - 4,
        y - 4,
        width + 8,
        height + 8,
        8,
        dim_color(CYAN, 0.16),
    )
    canvas.rect(
        x - 1,
        y - 1,
        width + 2,
        height + 2,
        dim_color(BLACK, 0.88),
    )

    canvas.blend_rgba(
        x,
        y,
        width,
        height,
        vision.preview_rgba,
        alpha=0.40,
    )

    # Tiny corner markers make the preview read as a deliberate camera HUD.
    marker = max(5, width // 12)
    color = dim_color(CYAN, 0.55)

    canvas.line(
        x,
        y,
        x + marker,
        y,
        color,
        1,
    )
    canvas.line(
        x,
        y,
        x,
        y + marker,
        color,
        1,
    )
    canvas.line(
        x + width - marker,
        y,
        x + width,
        y,
        color,
        1,
    )
    canvas.line(
        x + width,
        y,
        x + width,
        y + marker,
        color,
        1,
    )


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
    sensor_feed = None
    camera_vision = None
    test_oled = "--test-oled" in sys.argv[1:]

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

            root = tg.FrameLayout(activity)
            root.setdimensions(tg.View.MATCH_PARENT, tg.View.MATCH_PARENT)
            root.setbackgroundcolor(0xFF000000)

            image = tg.ImageView(activity, parent=root)
            image.setdimensions(tg.View.MATCH_PARENT, tg.View.MATCH_PARENT)
            image.setbackgroundcolor(0xFF000000)
            image.sendtouchevent(True)

            caption_view = tg.TextView(activity, "", parent=root)
            caption_view.setdimensions(tg.View.MATCH_PARENT, tg.View.MATCH_PARENT)
            caption_view.settextcolor(0xFFF2FFFF)
            caption_view.settextsize(17)
            caption_view.setgravity(1, 2)
            caption_view.setmargin(26, "left")
            caption_view.setmargin(26, "right")
            caption_view.setmargin(34, "bottom")
            caption_view.setclickable(False)

            time_view = tg.TextView(activity, "", parent=root)
            time_view.setdimensions(tg.View.MATCH_PARENT, tg.View.MATCH_PARENT)
            time_view.settextcolor(0xFF66F7FA)
            time_view.settextsize(16)
            time_view.setgravity(1, 0)
            time_view.setmargin(22, "top")
            time_view.setmargin(0, "right")
            time_view.setclickable(False)

            status_view = tg.TextView(activity, "", parent=root)
            status_view.setdimensions(tg.View.MATCH_PARENT, tg.View.MATCH_PARENT)
            status_view.settextcolor(0xFF7CEFF3)
            status_view.settextsize(13)
            status_view.setgravity(0, 0)
            status_view.setmargin(22, "top")
            status_view.setmargin(20, "left")
            status_view.setclickable(False)

            dims = [0, 0]
            for _ in range(200):
                dims = image.getdimensions()
                if dims and dims[0] > 0 and dims[1] > 0:
                    break
                time.sleep(0.01)

            if not dims or dims[0] <= 0 or dims[1] <= 0:
                dims = [1080, 2400]

            screen_w = int(dims[0])
            screen_h = int(dims[1])

            # termuxgui 0.1.6 does not expose arbitrary absolute positioning
            # for normal Views. Keep these overlays MATCH_PARENT and use the
            # supported TextView gravity + margins API. They stay transparent
            # so the native animation remains full-screen.
            caption_view.setdimensions(
                tg.View.MATCH_PARENT,
                tg.View.MATCH_PARENT,
            )
            caption_view.setgravity(1, 2)
            caption_view.setmargin(28, "left")
            caption_view.setmargin(28, "right")
            caption_view.setmargin(34, "bottom")

            time_view.setdimensions(
                tg.View.MATCH_PARENT,
                tg.View.MATCH_PARENT,
            )
            time_view.setgravity(1, 0)
            time_view.setmargin(22, "top")
            time_view.setmargin(0, "right")

            status_view.setdimensions(
                tg.View.MATCH_PARENT,
                tg.View.MATCH_PARENT,
            )
            status_view.setgravity(0, 0)
            status_view.setmargin(22, "top")
            status_view.setmargin(20, "left")

            buffer_w, buffer_h = choose_buffer_size(screen_w, screen_h)
            buffer = tg.Buffer(connection, buffer_w, buffer_h)
            image.setbuffer(buffer)

            face = RoboEyesFace()
            doodle_show = DoodleShow()
            oled_asset_show = OledAssetShow()
            camera_vision = CameraVision(interval=1.15)

            face.voice.say(
                "Desk Buddy online.",
                force=True,
            )
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

                sensor_feed = SensorFeed(face)
                sensor_feed.start()

                camera_vision.start()

                if test_oled:
                    if oled_asset_show.start():
                        print(
                            "Desk Buddy OLED test: loaded "
                            f"{oled_asset_show.total_frames} frames from "
                            f"{oled_asset_show.source_label()} at "
                            f"{oled_asset_show.frame_seconds * 1000:.0f} ms/frame"
                        )
                    else:
                        print(
                            "Desk Buddy OLED test failed: "
                            f"{oled_asset_show.load_error}"
                        )

                next_frame = time.monotonic()
                last_caption = None
                last_clock = None
                last_status = None

                while not stop.is_set():
                    now = time.monotonic()

                    vision = camera_vision.snapshot()

                    right_hand_five = camera_vision.consume_right_hand_five()
                    boredom = camera_vision.consume_boredom()

                    with face.lock:
                        face.set_camera_attention(
                            vision.face_present,
                            vision.face_x,
                            vision.face_y,
                        )

                        if (
                            boredom
                            and not doodle_show.active
                            and not oled_asset_show.active
                        ):
                            face.camera_bored_reaction()

                        if right_hand_five:
                            print(
                                "Desk Buddy vision: right-hand open palm confirmed "
                                f"(confidence={vision.open_palm_confidence:.2f})"
                            )

                            if face.state.sleeping:
                                face.wake_up()

                            if oled_asset_show.start():
                                doodle_show.stop()
                                print(
                                    "Desk Buddy OLED: playing "
                                    f"{oled_asset_show.total_frames} frames from "
                                    f"{oled_asset_show.source_label()}"
                                )
                                face.voice.say(
                                    "Right hand detected. Playing your OLED animation.",
                                    force=True,
                                )
                            else:
                                print(
                                    "Desk Buddy OLED load failed: "
                                    f"{oled_asset_show.load_error}"
                                )
                                doodle_show.start()
                                face.voice.say(
                                    "Right hand detected. Local OLED frames are missing, so I am using the fallback show.",
                                    force=True,
                                )

                        if oled_asset_show.active:
                            if not oled_asset_show.draw(canvas, now):
                                face.set_emotion(
                                    "happy",
                                    3.5,
                                )
                                face.draw(canvas, oled, now)

                        elif doodle_show.active:
                            if not doodle_show.draw(canvas, now):
                                face.set_emotion(
                                    "happy",
                                    3.5,
                                )
                                face.draw(canvas, oled, now)

                        else:
                            face.draw(canvas, oled, now)

                    draw_camera_preview(
                        canvas,
                        vision,
                    )

                    buffer.blit()
                    image.refresh()

                    caption = face.voice.caption()
                    if caption != last_caption:
                        caption_view.settext(caption)
                        last_caption = caption

                    clock = time_label()
                    if clock != last_clock:
                        time_view.settext(clock)
                        last_clock = clock

                    with face.lock:
                        if face.state.sleeping:
                            mode_label = "SLEEP"
                        elif oled_asset_show.active:
                            mode_label = "OLED SHOW"
                        elif doodle_show.active:
                            mode_label = "DOODLE"
                        elif face.scenes.current:
                            mode_label = face.scenes.current.upper()
                        else:
                            mode_label = face.state.mood_name.upper()

                    if vision.available:
                        if vision.right_hand_five_fingers:
                            camera_label = "CAM● RH5"
                        elif vision.right_hand_candidate:
                            camera_label = (
                                f"CAM RH{max(1, vision.finger_count)}?"
                            )
                        else:
                            camera_label = "CAM●" if vision.face_present else "CAM"
                    else:
                        camera_label = "CAM OFF"

                    status = f"{camera_label}   {mode_label}"
                    if status != last_status:
                        status_view.settext(status)
                        last_status = status

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

    finally:
        if camera_vision is not None:
            camera_vision.stop()

        if sensor_feed is not None:
            sensor_feed.stop()


if __name__ == "__main__":
    raise SystemExit(main())
