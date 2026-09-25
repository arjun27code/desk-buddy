#!/usr/bin/env python3
from __future__ import annotations

import argparse
import curses
import json
import math
import random
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

APP_NAME = "DESK BUDDY"
EMOTION_HOLD_SECONDS = 2.5
EMOTION_CYCLE = ["happy", "curious", "annoyed", "sad"]
CONFIG_DIR = Path.home() / ".config" / "desk-buddy"
CONFIG_FILE = CONFIG_DIR / "config.json"

WEATHER_CODES = {
    0: ("Clear", "happy"),
    1: ("Mostly clear", "happy"),
    2: ("Partly cloudy", "idle"),
    3: ("Cloudy", "idle"),
    45: ("Foggy", "sleepy"),
    48: ("Foggy", "sleepy"),
    51: ("Light drizzle", "sad"),
    53: ("Drizzle", "sad"),
    55: ("Heavy drizzle", "sad"),
    61: ("Light rain", "sad"),
    63: ("Rain", "sad"),
    65: ("Heavy rain", "sad"),
    71: ("Light snow", "surprised"),
    73: ("Snow", "surprised"),
    75: ("Heavy snow", "surprised"),
    80: ("Rain showers", "sad"),
    81: ("Rain showers", "sad"),
    82: ("Heavy showers", "surprised"),
    95: ("Thunderstorm", "surprised"),
    96: ("Storm with hail", "surprised"),
    99: ("Storm with hail", "surprised"),
}

MESSAGES = {
    "idle": [
        "watching the desk",
        "tiny brain online",
        "everything looks suspiciously normal",
        "desk duty active",
    ],
    "happy": [
        "boop received",
        "morale upgraded",
        "acceptable human interaction",
        "happy protocol enabled",
    ],
    "love": [
        "friend detected",
        "affection packet received",
        "you may boop again",
    ],
    "excited": [
        "energy spike",
        "maximum tiny robot enthusiasm",
        "attention acquired",
    ],
    "sleepy": [
        "low-power cuteness mode",
        "trying very hard to stay awake",
        "nap calculations in progress",
    ],
    "surprised": [
        "unexpected event detected",
        "that was not in the handbook",
        "wide-eye protocol",
    ],
    "focused": [
        "focus mode",
        "processing desk mysteries",
        "serious robot business",
    ],
    "curious": [
        "curiosity mode",
        "what is that",
        "checking the corner",
    ],
    "annoyed": [
        "mildly unimpressed",
        "robot patience reduced",
        "tiny horizontal complaint",
    ],
    "sad": [
        "rain mood",
        "small weather disappointment",
        "clouds have opinions",
    ],
    "suspicious": [
        "hmm",
        "investigating",
        "something is mildly questionable",
    ],
}

EYE_COLOR_NAMES = ["cyan", "magenta", "yellow", "green", "blue", "white"]
EYE_CURSES_COLORS = [
    curses.COLOR_CYAN,
    curses.COLOR_MAGENTA,
    curses.COLOR_YELLOW,
    curses.COLOR_GREEN,
    curses.COLOR_BLUE,
    curses.COLOR_WHITE,
]


@dataclass
class BatteryInfo:
    available: bool = False
    percentage: int | None = None
    status: str = ""
    plugged: str = ""
    temperature: float | None = None


@dataclass
class WeatherInfo:
    available: bool = False
    temperature: float | None = None
    apparent: float | None = None
    description: str = ""
    mood: str = ""
    location_label: str = ""


@dataclass
class State:
    mood: str = "idle"
    message: str = "waking up"
    mood_until: float = 0.0

    gaze_x: float = 0.0
    gaze_y: float = 0.0
    target_gaze_x: float = 0.0
    target_gaze_y: float = 0.0
    next_gaze: float = 0.0

    blinking: bool = False
    blink_started: float = 0.0
    blink_duration: float = 0.22
    next_blink: float = 0.0
    pending_double_blink: bool = False

    eye_color_index: int = 0
    emotion_cycle_index: int = 0

    next_message: float = 0.0
    hint_until: float = 0.0

    battery: BatteryInfo = field(default_factory=BatteryInfo)
    weather: WeatherInfo = field(default_factory=WeatherInfo)
    last_battery_check: float = 0.0
    last_weather_check: float = 0.0


def load_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(config: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")


def run_json_command(command: list[str], timeout: float = 5.0) -> dict[str, Any] | None:
    if shutil.which(command[0]) is None:
        return None

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0:
        return None

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def get_battery() -> BatteryInfo:
    payload = run_json_command(["termux-battery-status"])
    if not payload:
        return BatteryInfo()

    try:
        percentage = int(payload.get("percentage"))
    except (TypeError, ValueError):
        percentage = None

    try:
        temperature = float(payload.get("temperature"))
    except (TypeError, ValueError):
        temperature = None

    return BatteryInfo(
        available=True,
        percentage=percentage,
        status=str(payload.get("status", "")),
        plugged=str(payload.get("plugged", "")),
        temperature=temperature,
    )


def get_termux_location() -> tuple[float, float, str] | None:
    payload = run_json_command(
        ["termux-location", "-p", "network", "-r", "once"],
        timeout=12.0,
    )
    if not payload:
        return None

    try:
        lat = float(payload["latitude"])
        lon = float(payload["longitude"])
    except (KeyError, TypeError, ValueError):
        return None

    return lat, lon, "phone location"


def geocode_city(city: str) -> tuple[float, float, str] | None:
    params = urlencode(
        {
            "name": city,
            "count": 1,
            "language": "en",
            "format": "json",
        }
    )
    url = f"https://geocoding-api.open-meteo.com/v1/search?{params}"
    request = Request(url, headers={"User-Agent": "desk-buddy/2.0"})

    try:
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None

    results = payload.get("results") or []
    if not results:
        return None

    first = results[0]
    try:
        lat = float(first["latitude"])
        lon = float(first["longitude"])
    except (KeyError, TypeError, ValueError):
        return None

    label_parts = [str(first.get("name", city))]
    if first.get("admin1"):
        label_parts.append(str(first["admin1"]))
    elif first.get("country"):
        label_parts.append(str(first["country"]))

    return lat, lon, ", ".join(label_parts)


def fetch_weather(city: str | None) -> WeatherInfo:
    position = get_termux_location()
    if position is None and city:
        position = geocode_city(city)
    if position is None:
        return WeatherInfo()

    lat, lon, label = position
    params = urlencode(
        {
            "latitude": f"{lat:.5f}",
            "longitude": f"{lon:.5f}",
            "current": "temperature_2m,apparent_temperature,weather_code",
            "timezone": "auto",
        }
    )
    url = f"https://api.open-meteo.com/v1/forecast?{params}"
    request = Request(url, headers={"User-Agent": "desk-buddy/2.0"})

    try:
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return WeatherInfo()

    current = payload.get("current") or {}

    try:
        temp = float(current["temperature_2m"])
    except (KeyError, TypeError, ValueError):
        return WeatherInfo()

    try:
        apparent = float(current.get("apparent_temperature"))
    except (TypeError, ValueError):
        apparent = None

    try:
        code = int(current.get("weather_code", -1))
    except (TypeError, ValueError):
        code = -1

    description, mood = WEATHER_CODES.get(code, ("Weather", "idle"))
    return WeatherInfo(
        available=True,
        temperature=temp,
        apparent=apparent,
        description=description,
        mood=mood,
        location_label=label,
    )


def put_text(
    screen: curses.window,
    y: int,
    x: int,
    text: str,
    attr: int = 0,
    max_width: int | None = None,
) -> None:
    height, width = screen.getmaxyx()
    if y < 0 or y >= height or x >= width:
        return

    if x < 0:
        text = text[-x:]
        x = 0

    allowed = width - x - 1
    if max_width is not None:
        allowed = min(allowed, max_width)
    if allowed <= 0:
        return

    try:
        screen.addstr(y, x, text[:allowed], attr)
    except curses.error:
        pass


def centered(screen: curses.window, y: int, text: str, attr: int = 0) -> None:
    _, width = screen.getmaxyx()
    put_text(screen, y, max(0, (width - len(text)) // 2), text, attr)


def fill_cells(
    screen: curses.window,
    y: int,
    x: int,
    width: int,
    attr: int,
    char: str = " ",
) -> None:
    if width <= 0:
        return
    put_text(screen, y, x, char * width, attr, width)


def rounded_row_inset(row: int, height: int) -> int:
    if height <= 2:
        return 0
    edge = min(row, height - 1 - row)
    if edge == 0:
        return 2
    if edge == 1:
        return 1
    return 0


def draw_rounded_eye_block(
    screen: curses.window,
    x: int,
    y: int,
    width: int,
    height: int,
    eye_attr: int,
    pupil_attr: int,
    highlight_attr: int,
    gaze_x: float,
    gaze_y: float,
    pupil_scale: float = 1.0,
    top_mask: str | None = None,
    bottom_mask: bool = False,
) -> None:
    if width < 5 or height < 2:
        return

    for row in range(height):
        inset = rounded_row_inset(row, height)
        if top_mask == "left_down":
            inset_left = max(inset, max(0, 3 - row))
            inset_right = inset
        elif top_mask == "right_down":
            inset_left = inset
            inset_right = max(inset, max(0, 3 - row))
        else:
            inset_left = inset
            inset_right = inset

        row_width = width - inset_left - inset_right
        if row_width > 0:
            fill_cells(screen, y + row, x + inset_left, row_width, eye_attr)

    if bottom_mask and height >= 4:
        mask_rows = max(1, height // 3)
        for row in range(mask_rows):
            inset = row + 1
            w = max(0, width - inset * 2)
            fill_cells(
                screen,
                y + height - 1 - row,
                x + inset,
                w,
                curses.A_NORMAL,
            )

    pupil_w = max(3, int(width * 0.30 * pupil_scale))
    pupil_h = max(2, int(height * 0.38 * pupil_scale))
    pupil_w = min(pupil_w, max(2, width - 6))
    pupil_h = min(pupil_h, max(1, height - 3))

    max_dx = max(0, (width - pupil_w) // 2 - 2)
    max_dy = max(0, (height - pupil_h) // 2 - 1)

    pupil_x = x + (width - pupil_w) // 2 + int(round(gaze_x * max_dx))
    pupil_y = y + (height - pupil_h) // 2 + int(round(gaze_y * max_dy))

    for row in range(pupil_h):
        fill_cells(screen, pupil_y + row, pupil_x, pupil_w, pupil_attr)

    if pupil_w >= 3 and pupil_h >= 2:
        highlight_x = pupil_x + pupil_w - 1
        highlight_y = pupil_y
        fill_cells(screen, highlight_y, highlight_x, 1, highlight_attr)


def draw_heart_eye(
    screen: curses.window,
    center_x: int,
    center_y: int,
    size: int,
    heart_attr: int,
) -> None:
    width = max(9, size)
    height = max(5, size // 2)
    pattern = [
        "  ██   ██  ",
        " ████ ████ ",
        " █████████ ",
        "  ███████  ",
        "   █████   ",
        "    ███    ",
        "     █     ",
    ]

    scale_w = max(1, width // 11)
    scale_h = max(1, height // 7)
    rendered_h = len(pattern) * scale_h
    start_y = center_y - rendered_h // 2

    for py, row in enumerate(pattern):
        expanded = "".join((" " * scale_w if ch == " " else "█" * scale_w) for ch in row)
        start_x = center_x - len(expanded) // 2
        for sy in range(scale_h):
            put_text(screen, start_y + py * scale_h + sy, start_x, expanded, heart_attr)


def blink_open_ratio(state: State, now: float) -> float:
    if not state.blinking:
        return 1.0

    progress = (now - state.blink_started) / max(0.05, state.blink_duration)
    if progress >= 1.0:
        state.blinking = False
        if state.pending_double_blink:
            state.pending_double_blink = False
            state.next_blink = now + 0.16
        return 1.0

    if progress < 0.5:
        return max(0.08, 1.0 - progress * 2.0)
    return max(0.08, (progress - 0.5) * 2.0)


def trigger_blink(state: State, now: float) -> None:
    state.blinking = True
    state.blink_started = now
    state.blink_duration = random.uniform(0.18, 0.24)
    state.pending_double_blink = random.random() < 0.12
    state.next_blink = now + random.uniform(2.0, 6.0)


def update_motion(state: State, now: float) -> None:
    if not state.blinking and now >= state.next_blink:
        trigger_blink(state, now)

    if state.mood == "curious":
        state.target_gaze_x = 0.78
        state.target_gaze_y = -0.62
    elif state.mood == "sad":
        state.target_gaze_x = 0.0
        state.target_gaze_y = 0.78
    elif state.mood == "annoyed":
        state.target_gaze_x = -0.15
        state.target_gaze_y = 0.0
    elif state.mood in {"happy", "love"}:
        state.target_gaze_x = 0.0
        state.target_gaze_y = -0.10
    elif now >= state.next_gaze and not state.blinking:
        choices = [
            (0.0, 0.0),
            (0.0, 0.0),
            (0.0, 0.0),
            (-0.78, 0.0),
            (0.78, 0.0),
            (-0.60, -0.55),
            (0.60, -0.55),
            (-0.50, 0.50),
            (0.50, 0.50),
        ]
        state.target_gaze_x, state.target_gaze_y = random.choice(choices)
        state.next_gaze = now + random.uniform(0.5, 3.0)

    ease = 0.18 if state.mood == "idle" else 0.28
    state.gaze_x += (state.target_gaze_x - state.gaze_x) * ease
    state.gaze_y += (state.target_gaze_y - state.gaze_y) * ease


def eye_geometry(
    screen: curses.window,
    state: State,
    now: float,
) -> tuple[int, int, int, int, int]:
    height, width = screen.getmaxyx()

    available_w = max(28, min(width - 4, 68))
    gap = max(3, min(7, available_w // 10))
    eye_w = max(11, min(22, (available_w - gap) // 2))

    base_h = max(6, min(12, int(round(eye_w * 0.52))))
    breath = math.sin(now / 0.78) * 0.5
    base_h = max(4, base_h + int(round(breath)))

    if state.mood == "surprised":
        eye_w = max(10, eye_w - 3)
        base_h = min(13, base_h + 3)
    elif state.mood == "sleepy":
        base_h = max(3, base_h - 3)
        eye_w = min(24, eye_w + 1)
    elif state.mood == "excited":
        eye_w = min(24, eye_w + 2)
        base_h = min(13, base_h + 2)
    elif state.mood == "suspicious":
        base_h = max(4, base_h - 2)
    elif state.mood == "sad":
        base_h = max(4, base_h - 2)
    elif state.mood == "annoyed":
        base_h = max(4, base_h - 2)
    elif state.mood == "curious":
        eye_w = min(24, eye_w + 1)

    open_ratio = blink_open_ratio(state, now)
    draw_h = max(1, int(round(base_h * open_ratio)))

    total_w = eye_w * 2 + gap
    start_x = max(1, (width - total_w) // 2)

    face_center_y = height // 2 - 2
    start_y = max(4, face_center_y - draw_h // 2)

    return start_x, start_y, eye_w, draw_h, gap


def draw_face(
    screen: curses.window,
    state: State,
    colors: dict[str, Any],
    now: float,
) -> None:
    height, width = screen.getmaxyx()

    if height < 12 or width < 30:
        centered(screen, height // 2, "●   ●", colors["text"])
        return

    start_x, start_y, eye_w, eye_h, gap = eye_geometry(screen, state, now)

    if state.mood == "happy":
        start_y += int(round(math.sin(now * 14.0) * 1.2))
    elif state.mood == "annoyed":
        start_x += int(round(math.sin(now * 26.0) * 1.5))
    elif state.mood == "sad":
        start_y += 1

    right_x = start_x + eye_w + gap

    eye_attr = colors["eye_fills"][state.eye_color_index]
    pupil_attr = colors["pupil"]
    highlight_attr = colors["highlight"]

    if state.mood == "love":
        left_center = start_x + eye_w // 2
        right_center = right_x + eye_w // 2
        center_y = start_y + max(3, eye_h // 2)
        heart_attr = colors["love_fill"]
        draw_heart_eye(screen, left_center, center_y, eye_w, heart_attr)
        draw_heart_eye(screen, right_center, center_y, eye_w, heart_attr)
        return

    top_mask_left = None
    top_mask_right = None
    bottom_mask = state.mood == "happy"

    if state.mood in {"focused", "annoyed"}:
        top_mask_left = "left_down"
        top_mask_right = "right_down"
    elif state.mood == "sad":
        top_mask_left = "right_down"
        top_mask_right = "left_down"

    if state.mood == "suspicious":
        left_h = max(2, eye_h // 2)
        right_h = eye_h
        draw_rounded_eye_block(
            screen,
            start_x,
            start_y + (eye_h - left_h) // 2,
            eye_w,
            left_h,
            eye_attr,
            pupil_attr,
            highlight_attr,
            state.gaze_x,
            state.gaze_y,
            pupil_scale=0.9,
        )
        draw_rounded_eye_block(
            screen,
            right_x,
            start_y,
            eye_w,
            right_h,
            eye_attr,
            pupil_attr,
            highlight_attr,
            state.gaze_x,
            state.gaze_y,
            pupil_scale=0.9,
        )
        return

    pupil_scale = 0.82 if state.mood == "surprised" else 1.0

    draw_rounded_eye_block(
        screen,
        start_x,
        start_y,
        eye_w,
        eye_h,
        eye_attr,
        pupil_attr,
        highlight_attr,
        state.gaze_x,
        state.gaze_y,
        pupil_scale=pupil_scale,
        top_mask=top_mask_left,
        bottom_mask=bottom_mask,
    )
    draw_rounded_eye_block(
        screen,
        right_x,
        start_y,
        eye_w,
        eye_h,
        eye_attr,
        pupil_attr,
        highlight_attr,
        state.gaze_x,
        state.gaze_y,
        pupil_scale=pupil_scale,
        top_mask=top_mask_right,
        bottom_mask=bottom_mask,
    )


def draw_ui(
    screen: curses.window,
    state: State,
    colors: dict[str, Any],
    now: float,
) -> None:
    height, width = screen.getmaxyx()
    current = datetime.now()

    put_text(screen, 1, 2, APP_NAME, colors["label"] | curses.A_BOLD)

    time_text = current.strftime("%H:%M")
    put_text(
        screen,
        1,
        max(2, width - len(time_text) - 3),
        time_text,
        colors["text"] | curses.A_BOLD,
    )

    if height < 18:
        return

    status_bits: list[str] = []

    if state.battery.available and state.battery.percentage is not None:
        status_bits.append(f"BAT {state.battery.percentage}%")

    if state.weather.available and state.weather.temperature is not None:
        status_bits.append(
            f"{state.weather.description.upper()} {round(state.weather.temperature)}°C"
        )

    if status_bits:
        centered(screen, height - 4, "  •  ".join(status_bits), colors["label"])

    centered(screen, height - 3, state.message, colors["text"])

    if now <= state.hint_until:
        centered(
            screen,
            height - 2,
            "B boop  SPACE mood  W weather  S sleep  C color  H help  Q quit",
            colors["muted"],
        )


def set_mood(
    state: State,
    mood: str,
    duration: float = EMOTION_HOLD_SECONDS,
    message: str | None = None,
) -> None:
    state.mood = mood
    state.mood_until = time.monotonic() + duration
    state.message = message or random.choice(MESSAGES.get(mood, MESSAGES["idle"]))


def refresh_battery(state: State) -> None:
    state.battery = get_battery()
    state.last_battery_check = time.monotonic()

    if not state.battery.available:
        return

    percent = state.battery.percentage
    status = state.battery.status.lower()

    if "charging" in status:
        set_mood(state, "happy", 3.0, "charging")
    elif percent is not None and percent <= 15:
        set_mood(state, "focused", 4.0, "battery low")


def refresh_weather(
    state: State,
    city: str | None,
    manual: bool = False,
) -> None:
    state.weather = fetch_weather(city)
    state.last_weather_check = time.monotonic()

    if not state.weather.available:
        if manual:
            set_mood(
                state,
                "focused",
                4.0,
                "weather needs Termux:API location or a saved city",
            )
        return

    temp = state.weather.temperature or 0.0
    if manual:
        set_mood(
            state,
            state.weather.mood,
            4.0,
            f"{state.weather.description.lower()}  {round(temp)}°C",
        )
    elif state.weather.mood in {"sad", "surprised"}:
        set_mood(state, state.weather.mood, 4.0)


def init_colors() -> dict[str, Any]:
    colors: dict[str, Any] = {
        "eye_fills": [curses.A_REVERSE] * len(EYE_COLOR_NAMES),
        "pupil": curses.A_NORMAL,
        "highlight": curses.A_REVERSE | curses.A_BOLD,
        "love_fill": curses.A_BOLD,
        "text": curses.A_NORMAL,
        "label": curses.A_BOLD,
        "muted": curses.A_DIM,
    }

    if not curses.has_colors():
        return colors

    curses.start_color()
    try:
        curses.use_default_colors()
    except curses.error:
        pass

    eye_fills: list[int] = []
    pair = 1

    try:
        for color in EYE_CURSES_COLORS:
            curses.init_pair(pair, color, color)
            eye_fills.append(curses.color_pair(pair))
            pair += 1

        curses.init_pair(pair, curses.COLOR_BLACK, curses.COLOR_BLACK)
        colors["pupil"] = curses.color_pair(pair)
        pair += 1

        curses.init_pair(pair, curses.COLOR_WHITE, curses.COLOR_WHITE)
        colors["highlight"] = curses.color_pair(pair) | curses.A_BOLD
        pair += 1

        curses.init_pair(pair, curses.COLOR_MAGENTA, curses.COLOR_MAGENTA)
        colors["love_fill"] = curses.color_pair(pair)
        pair += 1

        curses.init_pair(pair, curses.COLOR_CYAN, curses.COLOR_BLACK)
        colors["text"] = curses.color_pair(pair)
        colors["label"] = curses.color_pair(pair) | curses.A_BOLD
        pair += 1

        curses.init_pair(pair, curses.COLOR_BLUE, curses.COLOR_BLACK)
        colors["muted"] = curses.color_pair(pair) | curses.A_BOLD

        colors["eye_fills"] = eye_fills
    except curses.error:
        pass

    return colors


def main_loop(screen: curses.window, city: str | None, config: dict[str, Any]) -> None:
    try:
        curses.curs_set(0)
    except curses.error:
        pass

    screen.nodelay(True)
    screen.keypad(True)
    screen.timeout(16)

    colors = init_colors()
    now = time.monotonic()

    color_index = int(config.get("eye_color_index", 0))
    color_index %= len(EYE_COLOR_NAMES)

    state = State(
        eye_color_index=color_index,
        next_blink=now + random.uniform(1.3, 3.5),
        next_gaze=now + random.uniform(0.4, 1.2),
        next_message=now + random.uniform(7.0, 12.0),
        hint_until=now + 8.0,
    )

    refresh_battery(state)
    refresh_weather(state, city)

    while True:
        now = time.monotonic()
        hour = datetime.now().hour

        update_motion(state, now)

        if state.mood != "idle" and now >= state.mood_until:
            state.mood = "idle"

        if state.mood == "idle" and (hour >= 23 or hour < 7):
            state.mood = "sleepy"

        if now >= state.next_message and state.mood in {"idle", "sleepy"}:
            pool = MESSAGES["sleepy"] if state.mood == "sleepy" else MESSAGES["idle"]
            state.message = random.choice(pool)
            state.next_message = now + random.uniform(9.0, 16.0)

        if now - state.last_battery_check >= 30.0:
            refresh_battery(state)

        if now - state.last_weather_check >= 600.0:
            refresh_weather(state, city)

        screen.erase()
        draw_face(screen, state, colors, now)
        draw_ui(screen, state, colors, now)
        screen.refresh()

        key = screen.getch()
        if key == -1:
            continue

        if key in (ord("q"), ord("Q")):
            break

        if key in (ord("b"), ord("B")):
            mood = EMOTION_CYCLE[state.emotion_cycle_index]
            state.emotion_cycle_index = (
                state.emotion_cycle_index + 1
            ) % len(EMOTION_CYCLE)
            set_mood(state, mood, EMOTION_HOLD_SECONDS)
            state.hint_until = max(state.hint_until, now + 2.0)
        elif key == ord(" "):
            set_mood(
                state,
                random.choice(
                    [
                        "happy",
                        "love",
                        "excited",
                        "surprised",
                        "focused",
                        "suspicious",
                        "curious",
                        "annoyed",
                        "sad",
                    ]
                ),
                EMOTION_HOLD_SECONDS,
            )
        elif key in (ord("s"), ord("S")):
            set_mood(state, "sleepy", 8.0)
        elif key in (ord("w"), ord("W")):
            state.message = "checking weather"
            screen.refresh()
            refresh_weather(state, city, manual=True)
        elif key in (ord("c"), ord("C")):
            state.eye_color_index = (state.eye_color_index + 1) % len(EYE_COLOR_NAMES)
            config["eye_color_index"] = state.eye_color_index
            save_config(config)
            set_mood(
                state,
                "happy",
                2.0,
                f"eyes: {EYE_COLOR_NAMES[state.eye_color_index]}",
            )
        elif key in (ord("h"), ord("H")):
            state.hint_until = now + 8.0
            state.message = "controls visible"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OLED-style animated Desk Buddy for Termux."
    )
    parser.add_argument(
        "--city",
        help="City used for weather when Termux:API location is unavailable.",
    )
    parser.add_argument(
        "--set-city",
        help="Save a default city for future runs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()

    if args.set_city:
        config["city"] = args.set_city.strip()
        save_config(config)
        print(f"Desk Buddy city saved: {config['city']}")
        return

    city = args.city or config.get("city")

    try:
        curses.wrapper(main_loop, city, config)
    except KeyboardInterrupt:
        pass
    finally:
        print("Desk Buddy is sleeping.")


if __name__ == "__main__":
    main()
