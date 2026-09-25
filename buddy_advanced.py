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

    SCENES = ["bike", "car", "walk", "park", "rainbow", "rain"]

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
    }

    def __init__(self, voice: BuddyVoice):
        self.voice = voice
        now = time.monotonic()
        self.current = ""
        self.started = 0.0
        self.until = 0.0
        self.next_scene = now + random.uniform(15.0, 30.0)
        self.last_scene = ""
        self.road_phase = 0.0
        self.walk_phase = 0.0
        self.rain_mode = "medium"
        self.rain: list[SceneParticle] = []
        self.rockets: list[SceneParticle] = []
        self.firework_sparks: list[SceneParticle] = []
        self.last_rocket = 0.0

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

    def _draw_stars(self, canvas, now: float, count: int = 22) -> None:
        for index in range(count):
            x = (index * 97 + 31) % max(1, canvas.width)
            y = (index * 53 + 17) % max(1, int(canvas.height * 0.58))
            pulse = 0.35 + 0.30 * math.sin(now * 1.7 + index)
            canvas.circle(x, y, 1.0 + (index % 3 == 0), dim_color(WHITE, pulse))

    def draw_sleep(self, canvas, now: float) -> None:
        self._draw_stars(canvas, now, 28)
        moon_x = canvas.width * 0.80
        moon_y = canvas.height * 0.16
        r = max(13.0, canvas.width * 0.055)
        canvas.circle(moon_x, moon_y, r, dim_color(WHITE, 0.78))
        canvas.circle(
            moon_x + r * 0.42,
            moon_y - r * 0.14,
            r * 0.92,
            BLACK,
        )

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
        self._draw_road(canvas, now, 0.95)
        bob = math.sin(now * 7.5) * 3.0
        y = canvas.height * 0.84 + bob
        left = canvas.width * 0.30
        right = canvas.width * 0.70
        handle_color = dim_color(CYAN, 0.55)

        canvas.line(left, y, canvas.width * 0.44, y - 28, handle_color, 4)
        canvas.line(right, y, canvas.width * 0.56, y - 28, handle_color, 4)
        canvas.line(
            canvas.width * 0.44,
            y - 28,
            canvas.width * 0.56,
            y - 28,
            handle_color,
            4,
        )

        for x in (canvas.width * 0.25, canvas.width * 0.75):
            canvas.circle(x, canvas.height * 0.93, canvas.width * 0.075, dim_color(CYAN, 0.20))
            canvas.circle(x, canvas.height * 0.93, canvas.width * 0.060, BLACK)

    def _draw_car(self, canvas, now: float) -> None:
        self._draw_road(canvas, now, 1.35)
        dashboard_y = canvas.height * 0.82
        canvas.rect(
            0,
            dashboard_y,
            canvas.width,
            canvas.height - dashboard_y,
            dim_color(CYAN, 0.045),
        )

        wheel_x = canvas.width / 2.0
        wheel_y = canvas.height * 0.90
        wheel_r = canvas.width * 0.12
        canvas.circle(wheel_x, wheel_y, wheel_r, dim_color(CYAN, 0.25))
        canvas.circle(wheel_x, wheel_y, wheel_r * 0.70, BLACK)
        canvas.line(
            wheel_x,
            wheel_y,
            wheel_x,
            wheel_y + wheel_r * 0.72,
            dim_color(CYAN, 0.25),
            4,
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
        colors = [RED, ORANGE, YELLOW, GREEN, CYAN, BLUE, PURPLE]
        cx = canvas.width / 2.0
        cy = canvas.height * 0.59
        base = canvas.width * 0.43
        thickness = max(4, int(canvas.width * 0.012))

        for index, color in enumerate(colors):
            radius = base - index * thickness * 1.6
            for angle_deg in range(202, 339, 2):
                angle = math.radians(angle_deg)
                x = cx + math.cos(angle) * radius
                y = cy + math.sin(angle) * radius * 0.66
                canvas.circle(
                    x,
                    y,
                    thickness * 0.72,
                    dim_color(color, 0.24 + 0.04 * math.sin(now + index)),
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
            self.draw_fullscreen_rain(canvas, dt, eye_color)

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
