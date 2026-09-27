#!/usr/bin/env python3
from __future__ import annotations

import math


# Geometry adapted from TheDeveloperOps/rant-engineer-projects
# IOT/CosmoEyesKeyChainProject.md.
# The source explicitly permits use/modification/sharing for personal or
# educational projects. This module ports the visual behavior to the native
# phone renderer rather than copying the ESP32/WiFi hardware stack.

VIRTUAL_WIDTH = 128
VIRTUAL_HEIGHT = 64

EYE_WIDTH = 34
EYE_HEIGHT = 40
EYE_RADIUS = 10
EYE_GAP = 12

LEFT_X = 24
RIGHT_X = 70
EYE_Y = 12

WHITE = (240, 255, 255, 255)
BLACK = (0, 0, 0, 255)

COSMO_MODES = {
    "idle",
    "normal",
    "happy",
    "surprised",
    "angry",
    "annoyed",
    "sleepy",
    "wink",
    "love",
    "lookleft",
    "lookright",
}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * clamp(t, 0.0, 1.0)


def _draw_pair(
    oled,
    *,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    left_h: float = EYE_HEIGHT,
    right_h: float = EYE_HEIGHT,
    left_w: float = EYE_WIDTH,
    right_w: float = EYE_WIDTH,
    radius: float = EYE_RADIUS,
    color=WHITE,
) -> tuple[float, float, float, float]:
    """Port of the original drawEyes geometry."""

    left_y = (
        EYE_Y
        + offset_y
        + (EYE_HEIGHT - left_h) / 2.0
    )
    right_y = (
        EYE_Y
        + offset_y
        + (EYE_HEIGHT - right_h) / 2.0
    )

    left_x = LEFT_X + offset_x
    right_x = RIGHT_X + offset_x

    oled.rounded_rect(
        left_x,
        left_y,
        left_w,
        left_h,
        radius,
        color,
    )
    oled.rounded_rect(
        right_x,
        right_y,
        right_w,
        right_h,
        radius,
        color,
    )

    return left_x, left_y, right_x, right_y


def _draw_heart(
    oled,
    cx: float,
    cy: float,
    size: float,
    color=WHITE,
) -> None:
    # The source uses integer arithmetic here:
    # int r = size / 3; then r / 2 and r / 3 also truncate.
    r = float(int(size) // 3)
    half_r = float(int(r) // 2)
    third_r = float(int(r) // 3)

    oled.circle(
        cx - r,
        cy - half_r,
        r,
        color,
    )
    oled.circle(
        cx + r,
        cy - half_r,
        r,
        color,
    )
    oled.polygon(
        [
            (
                cx - size,
                cy - third_r,
            ),
            (
                cx + size,
                cy - third_r,
            ),
            (
                cx,
                cy + size,
            ),
        ],
        color,
    )


def _look_offset(
    age: float,
    direction: float,
) -> float:
    """Phone-friendly timing for the sketch's lookAt() sequence."""

    cycle = 0.84
    t = age % cycle

    if t < 0.12:
        return direction * 18.0 * (t / 0.12)

    if t < 0.62:
        return direction * 18.0

    if t < 0.74:
        return direction * 18.0 * (
            1.0 - (t - 0.62) / 0.12
        )

    return 0.0


def _happy_geometry(
    age: float,
) -> tuple[float, float]:
    """Repeat the source happy shrink/hold/expand cycle."""

    cycle = 0.82
    t = age % cycle

    if t < 0.10:
        height = lerp(
            EYE_HEIGHT,
            EYE_HEIGHT / 2.0,
            t / 0.10,
        )
    elif t < 0.50:
        height = EYE_HEIGHT / 2.0
    elif t < 0.60:
        height = lerp(
            EYE_HEIGHT / 2.0,
            EYE_HEIGHT,
            (t - 0.50) / 0.10,
        )
    else:
        height = EYE_HEIGHT

    return height, EYE_HEIGHT / 4.0


def draw_cosmo(
    oled,
    *,
    mode: str,
    now: float,
    mode_started: float,
    idle_offset_x: float = 0.0,
    idle_offset_y: float = 0.0,
    idle_left_h: float = EYE_HEIGHT,
    idle_right_h: float = EYE_HEIGHT,
    tilt_x: float = 0.0,
    tilt_y: float = 0.0,
    color=WHITE,
    black=BLACK,
) -> None:
    """Draw one Cosmo-style eye frame."""

    normalized = mode.lower()
    if normalized == "normal":
        normalized = "idle"
    if normalized == "annoyed":
        normalized = "angry"

    age = max(
        0.0,
        now - mode_started,
    )

    physical_x = clamp(tilt_x, -1.0, 1.0) * 3.0
    physical_y = clamp(tilt_y, -1.0, 1.0) * 2.0

    if normalized == "idle":
        _draw_pair(
            oled,
            offset_x=idle_offset_x + physical_x,
            offset_y=idle_offset_y + physical_y,
            left_h=idle_left_h,
            right_h=idle_right_h,
            color=color,
        )
        return

    if normalized == "happy":
        height, down = _happy_geometry(age)
        _draw_pair(
            oled,
            offset_x=physical_x,
            offset_y=down + physical_y,
            left_h=height,
            right_h=height,
            color=color,
        )
        return

    if normalized == "surprised":
        oled.rounded_rect(
            LEFT_X - 3 + physical_x,
            EYE_Y - 5 + physical_y,
            EYE_WIDTH + 6,
            EYE_HEIGHT + 10,
            EYE_RADIUS,
            color,
        )
        oled.rounded_rect(
            RIGHT_X - 3 + physical_x,
            EYE_Y - 5 + physical_y,
            EYE_WIDTH + 6,
            EYE_HEIGHT + 10,
            EYE_RADIUS,
            color,
        )
        return

    if normalized == "angry":
        left_x, left_y, right_x, right_y = _draw_pair(
            oled,
            offset_x=physical_x,
            offset_y=physical_y,
            color=color,
        )

        oled.polygon(
            [
                (
                    left_x - 4,
                    left_y - 2,
                ),
                (
                    left_x + EYE_WIDTH,
                    left_y - 2,
                ),
                (
                    left_x - 4,
                    left_y + 14,
                ),
            ],
            black,
        )
        oled.polygon(
            [
                (
                    right_x + EYE_WIDTH + 4,
                    right_y - 2,
                ),
                (
                    right_x,
                    right_y - 2,
                ),
                (
                    right_x + EYE_WIDTH + 4,
                    right_y + 14,
                ),
            ],
            black,
        )
        return

    if normalized == "sleepy":
        _draw_pair(
            oled,
            offset_x=physical_x,
            offset_y=6 + physical_y,
            left_h=float(EYE_HEIGHT // 3),
            right_h=float(EYE_HEIGHT // 3),
            color=color,
        )
        return

    if normalized == "wink":
        _draw_pair(
            oled,
            offset_x=physical_x,
            offset_y=physical_y,
            left_h=6.0,
            right_h=EYE_HEIGHT,
            color=color,
        )
        return

    if normalized == "love":
        left_cx = LEFT_X + EYE_WIDTH / 2.0 + physical_x
        right_cx = RIGHT_X + EYE_WIDTH / 2.0 + physical_x
        cy = EYE_Y + EYE_HEIGHT / 2.0 + physical_y

        _draw_heart(
            oled,
            left_cx,
            cy,
            16.0,
            color,
        )
        _draw_heart(
            oled,
            right_cx,
            cy,
            16.0,
            color,
        )
        return

    if normalized in {"lookleft", "lookright"}:
        direction = (
            -1.0
            if normalized == "lookleft"
            else 1.0
        )
        look_x = _look_offset(
            age,
            direction,
        )

        _draw_pair(
            oled,
            offset_x=look_x + physical_x,
            offset_y=physical_y,
            color=color,
        )
        return

    _draw_pair(
        oled,
        offset_x=physical_x,
        offset_y=physical_y,
        color=color,
    )


class _FakeOLED:
    def __init__(self) -> None:
        self.ops: list[
            tuple[str, tuple, dict]
        ] = []

    def rounded_rect(self, *args, **kwargs) -> None:
        self.ops.append(
            (
                "rounded_rect",
                args,
                kwargs,
            )
        )

    def circle(self, *args, **kwargs) -> None:
        self.ops.append(
            (
                "circle",
                args,
                kwargs,
            )
        )

    def polygon(self, *args, **kwargs) -> None:
        self.ops.append(
            (
                "polygon",
                args,
                kwargs,
            )
        )


def run_self_test() -> None:
    oled = _FakeOLED()
    draw_cosmo(
        oled,
        mode="idle",
        now=10.0,
        mode_started=0.0,
    )

    assert len(oled.ops) == 2
    left = oled.ops[0][1]
    right = oled.ops[1][1]

    assert left[:6] == (
        24.0,
        12.0,
        34,
        40,
        10,
        WHITE,
    )
    assert right[:6] == (
        70.0,
        12.0,
        34,
        40,
        10,
        WHITE,
    )

    oled = _FakeOLED()
    draw_cosmo(
        oled,
        mode="surprised",
        now=10.0,
        mode_started=9.0,
    )
    left = oled.ops[0][1]
    right = oled.ops[1][1]

    assert left[:5] == (
        21.0,
        7.0,
        40,
        50,
        10,
    )
    assert right[:5] == (
        67.0,
        7.0,
        40,
        50,
        10,
    )

    oled = _FakeOLED()
    draw_cosmo(
        oled,
        mode="wink",
        now=10.0,
        mode_started=9.0,
    )
    assert oled.ops[0][1][3] == 6.0
    assert oled.ops[1][1][3] == 40

    oled = _FakeOLED()
    draw_cosmo(
        oled,
        mode="love",
        now=10.0,
        mode_started=9.0,
    )
    kinds = [
        item[0]
        for item in oled.ops
    ]
    assert kinds.count("circle") == 4
    assert kinds.count("polygon") == 2

    left = _FakeOLED()
    right = _FakeOLED()
    draw_cosmo(
        left,
        mode="lookleft",
        now=0.30,
        mode_started=0.0,
    )
    draw_cosmo(
        right,
        mode="lookright",
        now=0.30,
        mode_started=0.0,
    )
    assert left.ops[0][1][0] < LEFT_X
    assert right.ops[0][1][0] > LEFT_X

    print("Cosmo eyes self-test: PASS")


if __name__ == "__main__":
    import sys

    if "--self-test" in sys.argv:
        run_self_test()
