#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import random
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from gibber_voice import GibberVoice


BLACK = (0, 0, 0, 255)
CYAN = (18, 238, 242, 255)
WHITE = (240, 255, 255, 255)
YELLOW = (255, 214, 70, 255)
MAGENTA = (255, 65, 175, 255)
RED = (255, 70, 70, 255)
BLUE = (20, 90, 210, 255)
GREEN = (50, 205, 115, 255)
ORANGE = (255, 145, 45, 255)
PURPLE = (148, 80, 235, 255)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


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


class BuddyVoice:
    """Non-blocking Termux:API TTS plus a caption state for the UI."""

    def __init__(self):
        self.lock = threading.Lock()
        self.caption_text = ""
        self.caption_until = 0.0
        self.last_spoken_at = 0.0
        self.last_text = ""
        self.tts_available = shutil.which("termux-tts-speak") is not None
        self.process: subprocess.Popen[str] | None = None

    def say(
        self,
        text: str,
        *,
        caption_seconds: float = 4.5,
        force: bool = False,
        pitch: float = 1.18,
        rate: float = 1.02,
    ) -> None:
        now = time.monotonic()
        cleaned = " ".join(text.strip().split())
        if not cleaned:
            return

        with self.lock:
            self.caption_text = cleaned
            self.caption_until = now + caption_seconds

        if not self.tts_available:
            return

        if not force and now - self.last_spoken_at < 3.2:
            return

        if not force and cleaned == self.last_text and now - self.last_spoken_at < 12.0:
            return

        self.last_spoken_at = now
        self.last_text = cleaned

        try:
            self.process = subprocess.Popen(
                [
                    "termux-tts-speak",
                    "-p",
                    f"{pitch:.2f}",
                    "-r",
                    f"{rate:.2f}",
                    "-s",
                    "MUSIC",
                    cleaned,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except OSError:
            self.tts_available = False

    def caption(self) -> str:
        with self.lock:
            if time.monotonic() > self.caption_until:
                return ""
            return self.caption_text


# Keep the public name used by the rest of the project, but switch the audible
# layer from human TTS to local data-sound chirps. Captions remain real text.
BuddyVoice = GibberVoice


@dataclass
class SceneParticle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    ttl: float
    size: float
    color: tuple[int, int, int, int]


class SceneEngine:
    """Full-screen activity/background scenes behind the RoboEyes face."""

    SCENES = [
        "bike",
        "car",
        "walk",
        "park",
        "rainbow",
        "rain",
        "sunny",
        "night",
        "peek",
    ]

    SCENE_LINES = {
        "bike": [
            "Tiny bike ride.",
            "Helmet imaginary. Confidence real.",
            "Going for a ride.",
        ],
        "car": [
            "Road trip mode.",
            "Driving nowhere in particular.",
            "Tiny driver on duty.",
        ],
        "walk": [
            "Going for a little walk.",
            "Fresh air protocol.",
            "One tiny step at a time.",
        ],
        "park": [
            "Park break.",
            "Sitting quietly for a minute.",
            "This is a good bench.",
        ],
        "rainbow": [
            "Rainbow detected.",
            "The sky is showing off.",
            "Seven colors. Excessive, but acceptable.",
        ],
        "rain": [
            "Rainy day.",
            "I am staying dry in here.",
            "Weather has become dramatic.",
        ],
        "sunny": [
            "The sun came out.",
            "Suddenly very bright.",
            "Sunny mode.",
        ],
        "night": [
            "The stars are out.",
            "Night mode feels quiet.",
            "Moon inspection.",
        ],
        "peek": [
            "What is outside the screen?",
            "I am checking the edge.",
            "There must be something out there.",
        ],
    }

    def __init__(self, voice: BuddyVoice):
        self.voice = voice
        now = time.monotonic()
        self.current = ""
        self.started = 0.0
        self.until = 0.0
        self.next_scene = now + random.uniform(15.0, 30.0)
        self.last_scene = ""
        self.last_mood = "idle"
        self.road_phase = 0.0
        self.walk_phase = 0.0
        self.rain_mode = "medium"
        self.rain: list[SceneParticle] = []
        self.rockets: list[SceneParticle] = []
        self.firework_sparks: list[SceneParticle] = []
        self.last_rocket = 0.0
        self.peek_side = 1
        self.next_lightning = now + random.uniform(2.2, 5.0)
        self.lightning_until = 0.0

    def force(self, scene: str, duration: float | None = None) -> None:
        if scene not in self.SCENES:
            return
        now = time.monotonic()
        self.current = scene
        self.started = now
        self.until = now + (duration if duration is not None else random.uniform(8.0, 14.0))
        self.next_scene = self.until + random.uniform(18.0, 38.0)
        self.last_scene = scene

        if scene == "rain":
            self.rain_mode = random.choice(["slow", "medium", "fast"])
            self.rain.clear()
            self.next_lightning = now + random.uniform(2.0, 4.8)

        if scene == "peek":
            self.peek_side = random.choice([-1, 1])

        self.voice.say(random.choice(self.SCENE_LINES[scene]))

    def update(self, now: float, *, allow_random: bool, sleeping: bool) -> None:
        if sleeping:
            self.current = ""
            return

        if self.current and now >= self.until:
            self.current = ""
            self.next_scene = now + random.uniform(16.0, 35.0)

        if not allow_random or self.current:
            return

        if now < self.next_scene:
            return

        choices = [s for s in self.SCENES if s != self.last_scene]
        self.force(random.choice(choices))

    def _gradient(
        self,
        canvas,
        top: tuple[int, int, int, int],
        bottom: tuple[int, int, int, int],
        start_y: int = 0,
        end_y: int | None = None,
    ) -> None:
        end = canvas.height if end_y is None else max(start_y + 1, end_y)
        span = max(1, end - start_y)

        for y in range(start_y, min(canvas.height, end)):
            t = (y - start_y) / span
            color = (
                int(top[0] + (bottom[0] - top[0]) * t),
                int(top[1] + (bottom[1] - top[1]) * t),
                int(top[2] + (bottom[2] - top[2]) * t),
                255,
            )
            canvas.span(y, 0, canvas.width, color)

    def _cloud(
        self,
        canvas,
        x: float,
        y: float,
        size: float,
        strength: float = 0.18,
    ) -> None:
        color = dim_color(WHITE, strength)
        canvas.circle(x, y, size * 0.30, color)
        canvas.circle(x + size * 0.25, y - size * 0.12, size * 0.38, color)
        canvas.circle(x + size * 0.56, y, size * 0.31, color)
        canvas.rounded_rect(
            x - size * 0.16,
            y,
            size * 0.92,
            size * 0.34,
            size * 0.12,
            color,
        )

    def _draw_stars(self, canvas, now: float, count: int = 22) -> None:
        for index in range(count):
            x = (index * 97 + 31) % max(1, canvas.width)
            y = (index * 53 + 17) % max(1, int(canvas.height * 0.58))
            pulse = 0.35 + 0.30 * math.sin(now * 1.7 + index)
            canvas.circle(x, y, 1.0 + (index % 3 == 0), dim_color(WHITE, pulse))

    def draw_sleep(self, canvas, now: float) -> None:
        self._gradient(
            canvas,
            (2, 5, 16, 255),
            (0, 1, 7, 255),
        )
        self._draw_stars(canvas, now, 34)

        moon_x = canvas.width * 0.80
        moon_y = canvas.height * 0.14
        r = max(16.0, canvas.width * 0.060)
        canvas.circle(moon_x, moon_y, r * 1.20, dim_color(BLUE, 0.10))
        canvas.circle(moon_x, moon_y, r, dim_color(WHITE, 0.78))
        canvas.circle(
            moon_x + r * 0.42,
            moon_y - r * 0.14,
            r * 0.92,
            (2, 5, 16, 255),
        )

        # Tiny bed at the bottom. The main RoboEyes face is suppressed while
        # sleeping, so the bed becomes the actual character scene.
        floor_y = canvas.height * 0.83
        bed_x = canvas.width * 0.16
        bed_w = canvas.width * 0.68
        bed_h = canvas.height * 0.09

        canvas.rounded_rect(
            bed_x,
            floor_y,
            bed_w,
            bed_h,
            max(8, int(canvas.width * 0.025)),
            dim_color(CYAN, 0.20),
        )
        canvas.rounded_rect(
            bed_x + bed_w * 0.05,
            floor_y + bed_h * 0.12,
            bed_w * 0.24,
            bed_h * 0.52,
            max(6, int(canvas.width * 0.018)),
            dim_color(WHITE, 0.28),
        )

        blanket_x = bed_x + bed_w * 0.30
        canvas.rounded_rect(
            blanket_x,
            floor_y + bed_h * 0.14,
            bed_w * 0.63,
            bed_h * 0.62,
            max(6, int(canvas.width * 0.018)),
            dim_color(CYAN, 0.17),
        )

        # Mini sleeping head on the pillow.
        head_r = canvas.width * 0.052
        head_x = bed_x + bed_w * 0.20
        head_y = floor_y + bed_h * 0.38
        canvas.circle(head_x, head_y, head_r, dim_color(CYAN, 0.72))
        canvas.circle(head_x, head_y, max(1.0, head_r - 4), BLACK)

        eye_y = head_y
        eye_dx = head_r * 0.34
        eye_w = head_r * 0.28
        canvas.line(
            head_x - eye_dx - eye_w,
            eye_y,
            head_x - eye_dx + eye_w,
            eye_y,
            dim_color(CYAN, 0.92),
            max(1, int(head_r * 0.12)),
        )
        canvas.line(
            head_x + eye_dx - eye_w,
            eye_y,
            head_x + eye_dx + eye_w,
            eye_y,
            dim_color(CYAN, 0.92),
            max(1, int(head_r * 0.12)),
        )

        # Floating Z marks, moving upward rather than being static text.
        for index in range(3):
            phase = (now * 0.17 + index * 0.31) % 1.0
            x = head_x + head_r * 0.95 + phase * canvas.width * 0.12
            y = head_y - phase * canvas.height * 0.16 - index * 10
            size = max(6, int(8 + phase * 7))
            color = dim_color(CYAN, 0.25 + 0.45 * (1.0 - phase))
            canvas.line(x, y, x + size, y, color, 2)
            canvas.line(x + size, y, x, y + size, color, 2)
            canvas.line(x, y + size, x + size, y + size, color, 2)

    def _road_geometry(self, canvas):
        horizon = canvas.height * 0.42
        center = canvas.width / 2.0
        bottom_half = canvas.width * 0.48
        top_half = canvas.width * 0.07
        return horizon, center, bottom_half, top_half

    def _draw_road(self, canvas, now: float, speed: float) -> None:
        horizon, center, bottom_half, top_half = self._road_geometry(canvas)

        canvas.polygon(
            [
                (center - top_half, horizon),
                (center + top_half, horizon),
                (center + bottom_half, canvas.height),
                (center - bottom_half, canvas.height),
            ],
            dim_color(WHITE, 0.055),
        )

        phase = (now * speed) % 1.0
        for index in range(9):
            t = (index / 9.0 + phase) % 1.0
            eased = t * t
            y = horizon + eased * (canvas.height - horizon)
            length = 3.0 + eased * canvas.height * 0.055
            width = max(1, int(1 + eased * 4))
            canvas.line(
                center,
                y,
                center,
                min(canvas.height - 1, y + length),
                dim_color(WHITE, 0.45),
                width,
            )

    def _draw_bike(self, canvas, now: float) -> None:
        self._gradient(
            canvas,
            (2, 12, 20, 255),
            (0, 2, 7, 255),
            0,
            int(canvas.height * 0.72),
        )

        # Far skyline and trees move slower than the road for parallax.
        horizon = int(canvas.height * 0.42)
        city_phase = (now * 22.0) % 92.0
        for index in range(8):
            x = index * 92 - city_phase
            h = 38 + (index * 19) % 78
            canvas.rect(
                x,
                horizon - h,
                48 + (index % 3) * 13,
                h,
                dim_color(BLUE, 0.09 + (index % 2) * 0.025),
            )

        for index in range(6):
            x = (index * 137 - now * 52.0) % (canvas.width + 120) - 60
            canvas.rect(
                x,
                horizon - 45,
                7,
                45,
                dim_color(ORANGE, 0.10),
            )
            canvas.circle(
                x + 3,
                horizon - 62,
                24,
                dim_color(GREEN, 0.14),
            )

        self._draw_road(canvas, now, 1.10)

        # Speed streaks make the ride read immediately even when the phone is
        # standing upright on a desk.
        for index in range(13):
            y = horizon + ((index * 73 + int(now * 210)) % max(1, int(canvas.height - horizon)))
            side = -1 if index % 2 == 0 else 1
            x = canvas.width * (0.18 if side < 0 else 0.82)
            length = 18 + (index % 4) * 11
            canvas.line(
                x,
                y,
                x + side * length,
                y + length * 0.24,
                dim_color(CYAN, 0.10),
                2,
            )

        bob = math.sin(now * 7.5) * 4.0
        y = canvas.height * 0.84 + bob
        left = canvas.width * 0.25
        right = canvas.width * 0.75
        handle_color = dim_color(CYAN, 0.62)

        # Front-view handlebars and stem.
        canvas.line(left, y, canvas.width * 0.43, y - 35, handle_color, 5)
        canvas.line(right, y, canvas.width * 0.57, y - 35, handle_color, 5)
        canvas.line(
            canvas.width * 0.43,
            y - 35,
            canvas.width * 0.57,
            y - 35,
            handle_color,
            5,
        )
        canvas.line(
            canvas.width * 0.50,
            y - 35,
            canvas.width * 0.50,
            y + 38,
            dim_color(CYAN, 0.38),
            4,
        )

        # Wheels rotate as subtle rings.
        for wheel_index, x in enumerate((canvas.width * 0.22, canvas.width * 0.78)):
            wheel_y = canvas.height * 0.94
            outer = canvas.width * 0.078
            canvas.circle(x, wheel_y, outer, dim_color(CYAN, 0.24))
            canvas.circle(x, wheel_y, outer * 0.80, BLACK)

            for spoke in range(4):
                angle = now * 4.2 + spoke * math.pi / 2.0 + wheel_index
                canvas.line(
                    x,
                    wheel_y,
                    x + math.cos(angle) * outer * 0.72,
                    wheel_y + math.sin(angle) * outer * 0.72,
                    dim_color(CYAN, 0.18),
                    1,
                )

    def _draw_car(self, canvas, now: float) -> None:
        self._gradient(
            canvas,
            (3, 8, 19, 255),
            (0, 1, 5, 255),
            0,
            int(canvas.height * 0.76),
        )

        horizon = int(canvas.height * 0.40)
        city_phase = (now * 38.0) % 110.0

        for index in range(8):
            x = index * 110 - city_phase
            building_h = 55 + (index * 27) % 120
            building_w = 54 + (index % 3) * 18
            canvas.rect(
                x,
                horizon - building_h,
                building_w,
                building_h,
                dim_color(BLUE, 0.10),
            )

            for row in range(3):
                for column in range(2):
                    if (index + row + column + int(now)) % 3 == 0:
                        canvas.rect(
                            x + 9 + column * 18,
                            horizon - building_h + 14 + row * 22,
                            5,
                            8,
                            dim_color(YELLOW, 0.22),
                        )

        self._draw_road(canvas, now, 1.48)

        # Windshield frame.
        canvas.line(
            canvas.width * 0.05,
            canvas.height * 0.12,
            canvas.width * 0.18,
            canvas.height * 0.76,
            dim_color(CYAN, 0.12),
            3,
        )
        canvas.line(
            canvas.width * 0.95,
            canvas.height * 0.12,
            canvas.width * 0.82,
            canvas.height * 0.76,
            dim_color(CYAN, 0.12),
            3,
        )

        dashboard_y = canvas.height * 0.80
        canvas.rect(
            0,
            dashboard_y,
            canvas.width,
            canvas.height - dashboard_y,
            dim_color(CYAN, 0.055),
        )
        canvas.line(
            0,
            dashboard_y,
            canvas.width,
            dashboard_y,
            dim_color(CYAN, 0.22),
            2,
        )

        # Steering wheel turns gently.
        wheel_x = canvas.width / 2.0
        wheel_y = canvas.height * 0.90
        wheel_r = canvas.width * 0.125
        canvas.circle(wheel_x, wheel_y, wheel_r, dim_color(CYAN, 0.30))
        canvas.circle(wheel_x, wheel_y, wheel_r * 0.72, BLACK)

        angle = math.sin(now * 0.8) * 0.28
        for spoke in (0.0, 2.15, 4.15):
            a = spoke + angle
            canvas.line(
                wheel_x,
                wheel_y,
                wheel_x + math.cos(a) * wheel_r * 0.68,
                wheel_y + math.sin(a) * wheel_r * 0.68,
                dim_color(CYAN, 0.28),
                4,
            )

        # Instrument lights.
        for index, color in enumerate((CYAN, GREEN, YELLOW)):
            canvas.circle(
                canvas.width * (0.18 + index * 0.09),
                dashboard_y + 28,
                5,
                dim_color(color, 0.35),
            )

    def _draw_walk(self, canvas, now: float) -> None:
        ground = canvas.height * 0.72
        canvas.rect(
            0,
            ground,
            canvas.width,
            canvas.height - ground,
            dim_color(GREEN, 0.12),
        )

        speed = 68.0
        phase = (now * speed) % (canvas.width * 0.36)

        for index in range(5):
            x = index * canvas.width * 0.36 - phase
            while x < -canvas.width * 0.16:
                x += canvas.width * 1.8
            trunk = dim_color(ORANGE, 0.18)
            leaves = dim_color(GREEN, 0.28)
            canvas.rect(x, ground - 75, 8, 75, trunk)
            canvas.circle(x + 4, ground - 88, 31, leaves)

        for index in range(7):
            x = (index * canvas.width * 0.21 - phase * 1.5) % canvas.width
            y = ground + (index % 2) * 16
            canvas.line(
                x,
                y,
                x + 14,
                y + 2,
                dim_color(WHITE, 0.12),
                2,
            )

    def _draw_park(self, canvas, now: float) -> None:
        ground = canvas.height * 0.72
        canvas.rect(0, ground, canvas.width, canvas.height - ground, dim_color(GREEN, 0.14))

        trunk_x = canvas.width * 0.16
        canvas.rect(trunk_x, ground - 150, 14, 150, dim_color(ORANGE, 0.20))
        canvas.circle(trunk_x + 6, ground - 178, 65, dim_color(GREEN, 0.25))

        bench_y = ground - 18
        bench_x = canvas.width * 0.58
        canvas.rect(bench_x, bench_y, canvas.width * 0.30, 8, dim_color(ORANGE, 0.30))
        canvas.line(bench_x + 12, bench_y + 8, bench_x + 6, ground + 20, dim_color(ORANGE, 0.24), 4)
        canvas.line(
            bench_x + canvas.width * 0.27,
            bench_y + 8,
            bench_x + canvas.width * 0.28,
            ground + 20,
            dim_color(ORANGE, 0.24),
            4,
        )

        bird_y = canvas.height * 0.25
        bird_x = canvas.width * 0.68 + math.sin(now * 0.5) * 30
        canvas.line(bird_x - 10, bird_y, bird_x, bird_y - 5, dim_color(WHITE, 0.28), 2)
        canvas.line(bird_x, bird_y - 5, bird_x + 10, bird_y, dim_color(WHITE, 0.28), 2)

    def _draw_rainbow(self, canvas, now: float) -> None:
        self._gradient(
            canvas,
            (4, 19, 32, 255),
            (0, 4, 12, 255),
        )

        colors = [RED, ORANGE, YELLOW, GREEN, CYAN, BLUE, PURPLE]
        cx = canvas.width / 2.0
        cy = canvas.height * 0.68
        base = canvas.width * 0.47
        thickness = max(5, int(canvas.width * 0.014))

        # Soft halo under the rainbow makes it read on a tall phone screen.
        canvas.circle(
            cx,
            cy,
            base * 1.04,
            dim_color(WHITE, 0.018),
        )
        canvas.circle(
            cx,
            cy,
            base * 0.94,
            BLACK,
        )

        for index, color in enumerate(colors):
            radius = base - index * thickness * 1.55
            shimmer = 0.34 + 0.07 * math.sin(now * 1.7 + index)

            for angle_deg in range(202, 339, 2):
                angle = math.radians(angle_deg)
                x = cx + math.cos(angle) * radius
                y = cy + math.sin(angle) * radius * 0.67
                canvas.circle(
                    x,
                    y,
                    thickness * 0.70,
                    dim_color(color, shimmer),
                )

        self._cloud(
            canvas,
            canvas.width * 0.03,
            canvas.height * 0.61,
            canvas.width * 0.26,
            0.26,
        )
        self._cloud(
            canvas,
            canvas.width * 0.73,
            canvas.height * 0.61,
            canvas.width * 0.26,
            0.26,
        )

        # A few glints rather than turning the rainbow into a disco poster.
        for index in range(8):
            angle = now * 0.35 + math.tau * index / 8.0
            radius = base * 0.78
            x = cx + math.cos(angle) * radius
            y = cy + math.sin(angle) * radius * 0.66
            canvas.circle(
                x,
                y,
                2 + index % 2,
                dim_color(WHITE, 0.20 + 0.08 * math.sin(now * 2.0 + index)),
            )

    def _draw_sunny(self, canvas, now: float) -> None:
        self._gradient(
            canvas,
            (5, 30, 48, 255),
            (0, 7, 18, 255),
        )

        sun_x = canvas.width * 0.78
        sun_y = canvas.height * 0.18
        sun_r = canvas.width * 0.090

        for ring in range(4, 0, -1):
            canvas.circle(
                sun_x,
                sun_y,
                sun_r * (1.0 + ring * 0.28),
                dim_color(YELLOW, 0.018 * ring),
            )

        canvas.circle(
            sun_x,
            sun_y,
            sun_r,
            dim_color(YELLOW, 0.72),
        )

        for index in range(12):
            angle = now * 0.08 + math.tau * index / 12.0
            inner = sun_r * 1.35
            outer = sun_r * (1.75 + 0.08 * math.sin(now * 1.2 + index))
            canvas.line(
                sun_x + math.cos(angle) * inner,
                sun_y + math.sin(angle) * inner,
                sun_x + math.cos(angle) * outer,
                sun_y + math.sin(angle) * outer,
                dim_color(YELLOW, 0.28),
                2,
            )

        cloud_phase = (now * 11.0) % (canvas.width + 180)
        self._cloud(
            canvas,
            canvas.width + 80 - cloud_phase,
            canvas.height * 0.28,
            canvas.width * 0.19,
            0.18,
        )
        self._cloud(
            canvas,
            (canvas.width * 0.22 - cloud_phase * 0.45) % (canvas.width + 160) - 80,
            canvas.height * 0.38,
            canvas.width * 0.15,
            0.11,
        )

        # Warm horizon.
        ground = canvas.height * 0.78
        canvas.rect(
            0,
            ground,
            canvas.width,
            canvas.height - ground,
            dim_color(GREEN, 0.10),
        )

    def _draw_night(self, canvas, now: float) -> None:
        self._gradient(
            canvas,
            (3, 5, 22, 255),
            (0, 0, 6, 255),
        )
        self._draw_stars(canvas, now, 42)

        moon_x = canvas.width * 0.77
        moon_y = canvas.height * 0.16
        moon_r = canvas.width * 0.082
        canvas.circle(
            moon_x,
            moon_y,
            moon_r * 1.35,
            dim_color(BLUE, 0.07),
        )
        canvas.circle(
            moon_x,
            moon_y,
            moon_r,
            dim_color(WHITE, 0.72),
        )
        canvas.circle(
            moon_x + moon_r * 0.42,
            moon_y - moon_r * 0.16,
            moon_r * 0.92,
            (3, 5, 22, 255),
        )

        # Slow shooting star.
        phase = (now * 0.085) % 1.0
        sx = canvas.width * (0.05 + 0.72 * phase)
        sy = canvas.height * (0.23 + 0.10 * phase)
        canvas.line(
            sx - 55,
            sy - 24,
            sx,
            sy,
            dim_color(WHITE, 0.30),
            2,
        )

    def _draw_peek(self, canvas, now: float) -> None:
        # The face itself moves to the same edge in gui_buddy.py. This layer
        # adds a screen-edge lip and tiny gripping fingers.
        side = 1 if self.peek_side > 0 else -1
        x = canvas.width - 9 if side > 0 else 9

        canvas.rect(
            canvas.width - 13 if side > 0 else 0,
            0,
            13,
            canvas.height,
            dim_color(CYAN, 0.08),
        )
        canvas.line(
            x,
            0,
            x,
            canvas.height,
            dim_color(CYAN, 0.35),
            2,
        )

        base_y = canvas.height * 0.62
        wave = math.sin(now * 5.5) * 4.0

        for index in range(3):
            finger_y = base_y + index * 22
            canvas.line(
                x,
                finger_y,
                x - side * (18 + index * 3 + wave * 0.15),
                finger_y - 7,
                dim_color(CYAN, 0.48),
                4,
            )
            canvas.circle(
                x - side * (19 + index * 3 + wave * 0.15),
                finger_y - 7,
                3,
                dim_color(CYAN, 0.60),
            )

        # Little curiosity dots outside the apparent screen edge.
        for index in range(4):
            dot_x = x - side * (38 + index * 15)
            dot_y = canvas.height * 0.31 + math.sin(now * 2.0 + index) * 9
            canvas.circle(
                dot_x,
                dot_y,
                2 + index % 2,
                dim_color(CYAN, 0.16 + 0.05 * index),
            )

    def _draw_rain_atmosphere(
        self,
        canvas,
        now: float,
        dt: float,
        eye_color,
    ) -> None:
        age = max(0.0, now - self.started)

        self._gradient(
            canvas,
            (5, 10, 18, 255),
            (0, 1, 5, 255),
        )

        # Clouds arrive first. Rain starts after the buildup rather than
        # appearing from a black void.
        cloud_progress = min(1.0, age / 1.8)
        for index in range(5):
            target_x = canvas.width * (0.03 + index * 0.22)
            start_x = -canvas.width * (0.50 + index * 0.10)
            x = start_x + (target_x - start_x) * cloud_progress
            self._cloud(
                canvas,
                x,
                canvas.height * (0.12 + (index % 2) * 0.065),
                canvas.width * (0.23 + (index % 3) * 0.025),
                0.22,
            )

        if age >= 1.65:
            self.draw_fullscreen_rain(
                canvas,
                dt,
                eye_color,
            )

        if now >= self.next_lightning:
            self.lightning_until = now + random.uniform(0.10, 0.18)
            self.next_lightning = now + random.uniform(2.8, 6.8)

        if now < self.lightning_until:
            # Brief whole-screen flash and one branching bolt.
            canvas.rect(
                0,
                0,
                canvas.width,
                canvas.height,
                dim_color(WHITE, 0.10),
            )

            x = canvas.width * random.uniform(0.20, 0.82)
            y = canvas.height * 0.18
            segments = [
                (x, y),
                (x - 18, y + 65),
                (x + 3, y + 110),
                (x - 24, y + 175),
                (x - 10, y + 240),
            ]
            for start, end in zip(segments, segments[1:]):
                canvas.line(
                    start[0],
                    start[1],
                    end[0],
                    end[1],
                    dim_color(WHITE, 0.88),
                    3,
                )

    def _rain_profile(self):
        return {
            "slow": (55, 260.0, 390.0, 0.32),
            "medium": (100, 440.0, 650.0, 0.38),
            "fast": (165, 680.0, 940.0, 0.44),
        }[self.rain_mode]

    def _ensure_rain(self, canvas, eye_color) -> None:
        count, speed_low, speed_high, darkness = self._rain_profile()
        color = dim_color(eye_color, darkness)

        while len(self.rain) < count:
            self.rain.append(
                SceneParticle(
                    x=random.uniform(-20, canvas.width + 20),
                    y=random.uniform(-canvas.height, canvas.height),
                    vx=random.uniform(-90, -30),
                    vy=random.uniform(speed_low, speed_high),
                    life=random.uniform(22, 55),
                    ttl=99999,
                    size=random.uniform(1.0, 2.4),
                    color=color,
                )
            )

        if len(self.rain) > count:
            del self.rain[count:]

    def draw_fullscreen_rain(
        self,
        canvas,
        dt: float,
        eye_color,
        mode: str | None = None,
    ) -> None:
        if mode and mode != self.rain_mode:
            self.rain_mode = mode
            self.rain.clear()

        self._ensure_rain(canvas, eye_color)

        for drop in self.rain:
            drop.x += drop.vx * dt
            drop.y += drop.vy * dt

            if drop.y > canvas.height + 40 or drop.x < -60:
                drop.x = random.uniform(0, canvas.width + 80)
                drop.y = random.uniform(-canvas.height * 0.35, -10)

            length = drop.life
            canvas.line(
                drop.x,
                drop.y,
                drop.x - length * 0.18,
                drop.y + length,
                drop.color,
                max(1, int(round(drop.size))),
            )

    def _spawn_rocket(self, canvas) -> None:
        self.rockets.append(
            SceneParticle(
                x=random.uniform(canvas.width * 0.10, canvas.width * 0.90),
                y=canvas.height + 12,
                vx=random.uniform(-18, 18),
                vy=random.uniform(-720, -520),
                life=0.0,
                ttl=random.uniform(0.72, 1.05),
                size=random.uniform(2.0, 4.0),
                color=random.choice([CYAN, WHITE, YELLOW, MAGENTA, BLUE, RED, GREEN, ORANGE]),
            )
        )

    def _burst(self, rocket: SceneParticle) -> None:
        spokes = random.choice([20, 24, 28, 32])
        phase = random.uniform(0.0, math.tau)

        for index in range(spokes):
            angle = phase + math.tau * index / spokes + random.uniform(-0.06, 0.06)
            speed = random.uniform(120.0, 300.0)
            self.firework_sparks.append(
                SceneParticle(
                    x=rocket.x,
                    y=rocket.y,
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed,
                    life=0.0,
                    ttl=random.uniform(0.8, 1.55),
                    size=random.uniform(1.0, 2.5),
                    color=random.choice(
                        [rocket.color, CYAN, WHITE, YELLOW, MAGENTA, BLUE, RED, GREEN, ORANGE]
                    ),
                )
            )

    def draw_fireworks(self, canvas, now: float, dt: float) -> None:
        if now - self.last_rocket > random.uniform(0.42, 0.75):
            self.last_rocket = now
            self._spawn_rocket(canvas)

        active_rockets: list[SceneParticle] = []
        for rocket in self.rockets:
            rocket.life += dt
            rocket.x += rocket.vx * dt
            rocket.y += rocket.vy * dt
            rocket.vy += 170.0 * dt

            canvas.line(
                rocket.x,
                rocket.y + 4,
                rocket.x - rocket.vx * 0.035,
                rocket.y + 35,
                dim_color(rocket.color, 0.55),
                max(1, int(rocket.size * 0.7)),
            )
            canvas.circle(rocket.x, rocket.y, rocket.size, rocket.color)

            if rocket.life >= rocket.ttl or rocket.vy > -80:
                self._burst(rocket)
            else:
                active_rockets.append(rocket)
        self.rockets = active_rockets

        active_sparks: list[SceneParticle] = []
        for spark in self.firework_sparks:
            spark.life += dt
            if spark.life >= spark.ttl:
                continue

            spark.vy += 150.0 * dt
            spark.x += spark.vx * dt
            spark.y += spark.vy * dt
            fade = 1.0 - spark.life / spark.ttl

            canvas.line(
                spark.x - spark.vx * 0.022,
                spark.y - spark.vy * 0.022,
                spark.x,
                spark.y,
                dim_color(spark.color, fade),
                max(1, int(round(spark.size))),
            )
            active_sparks.append(spark)
        self.firework_sparks = active_sparks

    def draw(
        self,
        canvas,
        now: float,
        dt: float,
        *,
        mood: str,
        eye_color,
        sleeping: bool,
    ) -> None:
        if mood != self.last_mood:
            if mood == "sad":
                self.rain_mode = random.choice(["slow", "medium", "fast"])
                self.rain.clear()
            self.last_mood = mood

        if sleeping:
            self.draw_sleep(canvas, now)
            return

        if self.current == "bike":
            self._draw_bike(canvas, now)
        elif self.current == "car":
            self._draw_car(canvas, now)
        elif self.current == "walk":
            self._draw_walk(canvas, now)
        elif self.current == "park":
            self._draw_park(canvas, now)
        elif self.current == "rainbow":
            self._draw_rainbow(canvas, now)
        elif self.current == "rain":
            self._draw_rain_atmosphere(
                canvas,
                now,
                dt,
                eye_color,
            )
        elif self.current == "sunny":
            self._draw_sunny(canvas, now)
        elif self.current == "night":
            self._draw_night(canvas, now)
        elif self.current == "peek":
            self._draw_peek(canvas, now)

        # Emotion overlays take priority over the ambient scene.
        if mood == "sad":
            if random.random() < 0.0025:
                self.rain_mode = random.choice(["slow", "medium", "fast"])
                self.rain.clear()
            self.draw_fullscreen_rain(canvas, dt, eye_color)

        if mood == "happy":
            self.draw_fireworks(canvas, now, dt)


class SensorFusion:
    """Complementary accelerometer + gyroscope fusion for tilt and shake."""

    def __init__(self):
        self.roll = 0.0
        self.pitch = 0.0
        self.initialized = False
        self.baseline_roll: float | None = None
        self.baseline_pitch: float | None = None
        self.baseline_samples: list[tuple[float, float]] = []
        self.previous_accel: tuple[float, float, float] | None = None
        self.last_gyro_at: float | None = None
        self.last_shake_at = 0.0

    @staticmethod
    def _accel_angles(accel: tuple[float, float, float]) -> tuple[float, float]:
        ax, ay, az = accel
        roll = math.atan2(ay, az)
        pitch = math.atan2(-ax, math.sqrt(ay * ay + az * az))
        return roll, pitch

    @staticmethod
    def _angle_delta(value: float, baseline: float) -> float:
        diff = value - baseline
        while diff > math.pi:
            diff -= math.tau
        while diff < -math.pi:
            diff += math.tau
        return diff

    def update(
        self,
        *,
        accel: tuple[float, float, float] | None,
        gyro: tuple[float, float, float] | None,
        now: float,
    ) -> tuple[float, float, bool]:
        roll_acc = None
        pitch_acc = None

        if accel is not None:
            roll_acc, pitch_acc = self._accel_angles(accel)

        if not self.initialized and roll_acc is not None and pitch_acc is not None:
            self.roll = roll_acc
            self.pitch = pitch_acc
            self.initialized = True

        if gyro is not None and self.initialized:
            if self.last_gyro_at is not None:
                dt = clamp(now - self.last_gyro_at, 0.0, 0.15)
                gx, gy, _gz = gyro
                self.roll += gx * dt
                self.pitch += gy * dt
            self.last_gyro_at = now

        if self.initialized and roll_acc is not None and pitch_acc is not None:
            # Gyro carries fast motion, gravity vector corrects drift.
            alpha = 0.94 if gyro is not None else 0.0
            self.roll = alpha * self.roll + (1.0 - alpha) * roll_acc
            self.pitch = alpha * self.pitch + (1.0 - alpha) * pitch_acc

        if self.initialized and self.baseline_roll is None:
            self.baseline_samples.append((self.roll, self.pitch))
            if len(self.baseline_samples) >= 24:
                self.baseline_roll = sum(v[0] for v in self.baseline_samples) / len(self.baseline_samples)
                self.baseline_pitch = sum(v[1] for v in self.baseline_samples) / len(self.baseline_samples)

        tilt_x = 0.0
        tilt_y = 0.0
        if self.baseline_roll is not None and self.baseline_pitch is not None:
            delta_pitch = self._angle_delta(self.pitch, self.baseline_pitch)
            delta_roll = self._angle_delta(self.roll, self.baseline_roll)
            max_angle = math.radians(28.0)
            tilt_x = clamp(delta_pitch / max_angle, -1.0, 1.0)
            tilt_y = clamp(delta_roll / max_angle, -1.0, 1.0)

        shake = False
        jerk = 0.0

        if accel is not None and self.previous_accel is not None:
            ax, ay, az = accel
            px, py, pz = self.previous_accel
            jerk = math.sqrt((ax - px) ** 2 + (ay - py) ** 2 + (az - pz) ** 2)

        if accel is not None:
            self.previous_accel = accel

        gyro_speed = 0.0
        if gyro is not None:
            gx, gy, gz = gyro
            gyro_speed = math.sqrt(gx * gx + gy * gy + gz * gz)

        # Require a meaningful inertial event, but allow either sensor to lead.
        if (
            (jerk >= 5.0 and gyro_speed >= 1.4)
            or jerk >= 8.0
            or gyro_speed >= 6.0
        ) and now - self.last_shake_at >= 1.5:
            shake = True
            self.last_shake_at = now

        return tilt_x, tilt_y, shake


def discover_sensor_request() -> str:
    """Pick actual accelerometer/gyroscope names from termux-sensor -l."""
    if shutil.which("termux-sensor") is None:
        return ""

    try:
        result = subprocess.run(
            ["termux-sensor", "-l"],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
        if result.returncode != 0:
            return "Accelerometer,Gyroscope"

        payload = json.loads(result.stdout)
        sensors = payload.get("sensors") or []
    except Exception:
        return "Accelerometer,Gyroscope"

    accelerometers = [
        str(name)
        for name in sensors
        if "accelerometer" in str(name).lower()
    ]
    gyroscopes = [
        str(name)
        for name in sensors
        if "gyroscope" in str(name).lower()
        and "uncalibrated" not in str(name).lower()
    ]

    if not gyroscopes:
        gyroscopes = [
            str(name)
            for name in sensors
            if "gyro" in str(name).lower()
        ]

    selected: list[str] = []
    if accelerometers:
        selected.append(min(accelerometers, key=len))
    if gyroscopes:
        selected.append(min(gyroscopes, key=len))

    return ",".join(selected) if selected else "Accelerometer,Gyroscope"


def time_label() -> str:
    return datetime.now().strftime("%H:%M")
