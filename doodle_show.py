#!/usr/bin/env python3
from __future__ import annotations

import math
import random
import time


FRAME_SECONDS = 0.064
TOTAL_FRAMES = 102

BLACK = (0, 0, 0, 255)
CYAN = (18, 238, 242, 255)
WHITE = (245, 255, 255, 255)
MAGENTA = (255, 65, 175, 255)
YELLOW = (255, 214, 70, 255)


def dim(
    color: tuple[int, int, int, int],
    strength: float,
) -> tuple[int, int, int, int]:
    s = max(0.0, min(1.0, strength))
    return (
        int(color[0] * s),
        int(color[1] * s),
        int(color[2] * s),
        255,
    )


class DoodleShow:
    """Original 128x64-inspired hand-drawn animation.

    The timing language follows the uploaded OLED material: discrete 64 ms
    frames, simple black/white/cyan forms, expressive pose changes and tiny
    handmade jitter. The artwork itself is original rather than a copy of the
    uploaded lyric frames.
    """

    def __init__(self) -> None:
        self.active = False
        self.started = 0.0
        self.seed = 0

    def start(self) -> None:
        self.active = True
        self.started = time.monotonic()
        self.seed = random.randrange(1_000_000)

    def stop(self) -> None:
        self.active = False

    def frame_index(self, now: float) -> int:
        if not self.active:
            return -1
        return int((now - self.started) / FRAME_SECONDS)

    def draw(self, canvas, now: float) -> bool:
        frame = self.frame_index(now)
        if frame < 0:
            return False

        if frame >= TOTAL_FRAMES:
            self.active = False
            return False

        canvas.clear()

        progress = frame / max(1, TOTAL_FRAMES - 1)
        pulse = 0.5 + 0.5 * math.sin(frame * 0.52)

        self._background(canvas, frame, pulse)
        self._character(canvas, frame, progress)

        return True

    def _background(self, canvas, frame: int, pulse: float) -> None:
        # Sparse sketch dust so the full screen feels authored, not empty.
        for index in range(18):
            x = (index * 73 + self.seed * 3) % max(1, canvas.width)
            y = (
                index * 131
                + self.seed
                + frame * (1 + index % 3)
            ) % max(1, canvas.height)

            if (frame + index) % 5:
                continue

            canvas.circle(
                x,
                y,
                1 + (index % 2),
                dim(CYAN, 0.10 + 0.12 * pulse),
            )

    def _character(
        self,
        canvas,
        frame: int,
        progress: float,
    ) -> None:
        width = canvas.width
        height = canvas.height

        cx = width * 0.50
        cy = height * 0.47

        scale = min(width / 400.0, height / 860.0)

        jitter_x = math.sin(frame * 2.71 + self.seed) * 1.8 * scale
        jitter_y = math.sin(frame * 1.93 + self.seed * 0.7) * 1.4 * scale

        cx += jitter_x
        cy += jitter_y

        if frame < 15:
            # Pop in from tiny to full character.
            t = frame / 14.0
            pop = 1.0 - (1.0 - t) ** 3
            body_scale = 0.35 + pop * 0.65
            pose = "hello"

        elif frame < 30:
            body_scale = 1.0 + math.sin((frame - 15) * 0.45) * 0.035
            pose = "wave"

        elif frame < 45:
            body_scale = 1.0
            pose = "shy"

        elif frame < 60:
            body_scale = 1.0 + math.sin((frame - 45) * 0.40) * 0.025
            pose = "heart"

        elif frame < 75:
            body_scale = 1.0
            pose = "flop"

        elif frame < 90:
            t = (frame - 75) / 14.0
            body_scale = 0.92 + 0.08 * t
            pose = "recover"

        else:
            body_scale = 1.0 + math.sin((frame - 90) * 0.80) * 0.06
            pose = "celebrate"

        self._draw_figure(
            canvas,
            cx,
            cy,
            120 * scale * body_scale,
            pose,
            frame,
        )

    def _draw_figure(
        self,
        canvas,
        cx: float,
        cy: float,
        size: float,
        pose: str,
        frame: int,
    ) -> None:
        head_r = size * 0.27
        body_len = size * 0.42

        if pose == "flop":
            angle = math.radians(78)
        elif pose == "shy":
            angle = math.radians(-10)
        else:
            angle = 0.0

        head_x = cx
        head_y = cy - size * 0.18

        if pose == "flop":
            head_x -= size * 0.12
            head_y += size * 0.20

        outline = dim(CYAN, 0.90)
        soft = dim(CYAN, 0.35)

        canvas.circle(head_x, head_y, head_r + 4, soft)
        canvas.circle(head_x, head_y, head_r, outline)
        canvas.circle(head_x, head_y, max(1.0, head_r - 5), BLACK)

        # Eyes deliberately carry most of the acting.
        eye_y = head_y - head_r * 0.08

        if pose == "shy":
            eye_dx = head_r * 0.27
            canvas.line(
                head_x - eye_dx - head_r * 0.12,
                eye_y,
                head_x - eye_dx + head_r * 0.12,
                eye_y + head_r * 0.04,
                WHITE,
                max(1, int(size * 0.025)),
            )
            canvas.line(
                head_x + eye_dx - head_r * 0.12,
                eye_y + head_r * 0.04,
                head_x + eye_dx + head_r * 0.12,
                eye_y,
                WHITE,
                max(1, int(size * 0.025)),
            )

        elif pose == "heart":
            self._heart(
                canvas,
                head_x - head_r * 0.31,
                eye_y,
                head_r * 0.18,
                MAGENTA,
            )
            self._heart(
                canvas,
                head_x + head_r * 0.31,
                eye_y,
                head_r * 0.18,
                MAGENTA,
            )

        else:
            eye_r = head_r * (0.13 if pose != "celebrate" else 0.16)
            canvas.circle(head_x - head_r * 0.31, eye_y, eye_r, WHITE)
            canvas.circle(head_x + head_r * 0.31, eye_y, eye_r, WHITE)

            if pose in {"hello", "wave", "celebrate"}:
                canvas.circle(
                    head_x - head_r * 0.27,
                    eye_y - eye_r * 0.32,
                    max(1.0, eye_r * 0.30),
                    CYAN,
                )
                canvas.circle(
                    head_x + head_r * 0.35,
                    eye_y - eye_r * 0.32,
                    max(1.0, eye_r * 0.30),
                    CYAN,
                )

        neck_y = head_y + head_r
        body_end_x = neck_y * 0.0 + cx + math.sin(angle) * body_len
        body_end_y = neck_y + math.cos(angle) * body_len

        canvas.line(
            head_x,
            neck_y,
            body_end_x,
            body_end_y,
            outline,
            max(2, int(size * 0.030)),
        )

        shoulder_y = neck_y + body_len * 0.20

        if pose == "wave":
            wave = math.sin(frame * 0.95)
            canvas.line(
                cx,
                shoulder_y,
                cx - size * 0.31,
                shoulder_y + size * 0.10,
                outline,
                max(2, int(size * 0.026)),
            )
            canvas.line(
                cx,
                shoulder_y,
                cx + size * 0.25,
                shoulder_y - size * 0.20,
                outline,
                max(2, int(size * 0.026)),
            )
            self._tiny_hand(
                canvas,
                cx + size * 0.25,
                shoulder_y - size * 0.20,
                size * 0.11,
                wave,
            )

        elif pose == "shy":
            canvas.line(
                cx,
                shoulder_y,
                cx - size * 0.16,
                shoulder_y + size * 0.22,
                outline,
                max(2, int(size * 0.026)),
            )
            canvas.line(
                cx,
                shoulder_y,
                cx + size * 0.16,
                shoulder_y + size * 0.22,
                outline,
                max(2, int(size * 0.026)),
            )

        elif pose == "heart":
            self._heart(
                canvas,
                cx,
                shoulder_y + size * 0.08,
                size * 0.16,
                MAGENTA,
            )
            canvas.line(
                cx,
                shoulder_y,
                cx - size * 0.18,
                shoulder_y + size * 0.10,
                outline,
                max(2, int(size * 0.026)),
            )
            canvas.line(
                cx,
                shoulder_y,
                cx + size * 0.18,
                shoulder_y + size * 0.10,
                outline,
                max(2, int(size * 0.026)),
            )

        elif pose == "celebrate":
            canvas.line(
                cx,
                shoulder_y,
                cx - size * 0.28,
                shoulder_y - size * 0.22,
                outline,
                max(2, int(size * 0.026)),
            )
            canvas.line(
                cx,
                shoulder_y,
                cx + size * 0.28,
                shoulder_y - size * 0.22,
                outline,
                max(2, int(size * 0.026)),
            )

            for index in range(6):
                theta = frame * 0.20 + index * math.tau / 6.0
                hx = head_x + math.cos(theta) * size * 0.45
                hy = head_y + math.sin(theta) * size * 0.31
                self._heart(
                    canvas,
                    hx,
                    hy,
                    size * 0.055,
                    [MAGENTA, YELLOW, CYAN][index % 3],
                )

        else:
            canvas.line(
                cx,
                shoulder_y,
                cx - size * 0.24,
                shoulder_y + size * 0.12,
                outline,
                max(2, int(size * 0.026)),
            )
            canvas.line(
                cx,
                shoulder_y,
                cx + size * 0.24,
                shoulder_y + size * 0.12,
                outline,
                max(2, int(size * 0.026)),
            )

        leg_y = body_end_y
        if pose != "flop":
            canvas.line(
                body_end_x,
                leg_y,
                body_end_x - size * 0.15,
                leg_y + size * 0.24,
                outline,
                max(2, int(size * 0.026)),
            )
            canvas.line(
                body_end_x,
                leg_y,
                body_end_x + size * 0.15,
                leg_y + size * 0.24,
                outline,
                max(2, int(size * 0.026)),
            )

    def _tiny_hand(
        self,
        canvas,
        x: float,
        y: float,
        size: float,
        wave: float,
    ) -> None:
        canvas.circle(x, y, size * 0.24, CYAN)

        for index, angle in enumerate((-1.0, -0.55, -0.10, 0.35, 0.80)):
            theta = angle + wave * 0.18
            canvas.line(
                x,
                y,
                x + math.cos(theta) * size,
                y - math.sin(theta) * size,
                CYAN,
                max(1, int(size * 0.12)),
            )

    def _heart(
        self,
        canvas,
        x: float,
        y: float,
        size: float,
        color: tuple[int, int, int, int],
    ) -> None:
        points = [
            (x, y + size),
            (x - size, y - size * 0.05),
            (x - size * 0.80, y - size * 0.72),
            (x - size * 0.35, y - size),
            (x, y - size * 0.48),
            (x + size * 0.35, y - size),
            (x + size * 0.80, y - size * 0.72),
            (x + size, y - size * 0.05),
        ]
        canvas.polygon(points, color)
