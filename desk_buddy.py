#!/usr/bin/env python3
from __future__ import annotations

import argparse
import curses
import json
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

APP_NAME = "Desk Buddy"
CONFIG_DIR = Path.home() / ".config" / "desk-buddy"
CONFIG_FILE = CONFIG_DIR / "config.json"

WEATHER_CODES = {
    0: ("Clear", "sunny"),
    1: ("Mostly clear", "sunny"),
    2: ("Partly cloudy", "cloudy"),
    3: ("Cloudy", "cloudy"),
    45: ("Foggy", "foggy"),
    48: ("Foggy", "foggy"),
    51: ("Light drizzle", "rainy"),
    53: ("Drizzle", "rainy"),
    55: ("Heavy drizzle", "rainy"),
    61: ("Light rain", "rainy"),
    63: ("Rain", "rainy"),
    65: ("Heavy rain", "rainy"),
    71: ("Light snow", "snowy"),
    73: ("Snow", "snowy"),
    75: ("Heavy snow", "snowy"),
    80: ("Rain showers", "rainy"),
    81: ("Rain showers", "rainy"),
    82: ("Heavy showers", "stormy"),
    95: ("Thunderstorm", "stormy"),
    96: ("Storm with hail", "stormy"),
    99: ("Storm with hail", "stormy"),
}

MESSAGES = {
    "idle": [
        "desk duty active",
        "watching absolutely everything",
        "tiny brain, serious responsibilities",
        "all systems suspiciously calm",
    ],
    "happy": [
        "boop received",
        "energy level: excellent",
        "acceptable human interaction",
        "morale upgraded",
    ],
    "sleepy": [
        "low-power cuteness mode",
        "pretending not to fall asleep",
        "night shift is rude",
    ],
    "surprised": [
        "unexpected event detected",
        "that was not in the handbook",
        "attention acquired",
    ],
    "focused": [
        "focus mode",
        "processing desk mysteries",
        "concentration face activated",
    ],
    "rainy": [
        "rain outside. staying put.",
        "weather says: indoor creature",
    ],
}


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
    gaze_x: int = 0
    gaze_y: int = 0
    blink_until: float = 0.0
    mood_until: float = 0.0
    next_blink: float = 0.0
    next_gaze: float = 0.0
    next_message: float = 0.0
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

    percentage = payload.get("percentage")
    temperature = payload.get("temperature")

    try:
        percentage = int(percentage) if percentage is not None else None
    except (TypeError, ValueError):
        percentage = None

    try:
        temperature = float(temperature) if temperature is not None else None
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
    request = Request(url, headers={"User-Agent": "desk-buddy/1.0"})

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
    admin = first.get("admin1")
    country = first.get("country")

    if admin:
        label_parts.append(str(admin))
    elif country:
        label_parts.append(str(country))

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
    request = Request(url, headers={"User-Agent": "desk-buddy/1.0"})

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

    apparent_raw = current.get("apparent_temperature")

    try:
        apparent = float(apparent_raw) if apparent_raw is not None else None
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
    x = max(0, (width - len(text)) // 2)
    put_text(screen, y, x, text, attr)


def draw_small_face(screen: curses.window, state: State, colors: dict[str, int]) -> None:
    height, _ = screen.getmaxyx()
    eye = "▰" if time.monotonic() >= state.blink_until else "━"

    if state.mood == "sleepy":
        eye = "━"
    elif state.mood == "surprised":
        eye = "●"

    centered(
        screen,
        max(1, height // 2 - 1),
        f"{eye}   {eye}",
        colors["eye"] | curses.A_BOLD,
    )

    mouth = "⌣" if state.mood == "happy" else "·"
    centered(
        screen,
        max(2, height // 2 + 1),
        mouth,
        colors["accent"] | curses.A_BOLD,
    )


def eye_rows(state: State, blink: bool) -> list[str]:
    if blink or state.mood == "sleepy":
        return [
            "           ",
            "           ",
            "  ━━━━━━━  ",
            "           ",
            "           ",
        ]

    if state.mood == "surprised":
        return [
            "   ╭───╮   ",
            "  ╭╯   ╰╮  ",
            "  │  ●  │  ",
            "  ╰╮   ╭╯  ",
            "   ╰───╯   ",
        ]

    if state.mood == "happy":
        return [
            "           ",
            " ╲       ╱ ",
            "  ╲     ╱  ",
            "   ╲___╱   ",
            "           ",
        ]

    brow = "  ╲─────╱  " if state.mood == "focused" else "           "

    pupil_x = max(2, min(8, 5 + state.gaze_x))
    pupil_y = max(1, min(3, 2 + state.gaze_y))

    rows = [
        list(brow),
        list(" │       │ "),
        list(" │       │ "),
        list(" │       │ "),
        list(" ╰───────╯ "),
    ]

    if state.mood != "focused":
        rows[0] = list(" ╭───────╮ ")

    rows[pupil_y][pupil_x] = "●"

    return ["".join(row) for row in rows]


def draw_face(screen: curses.window, state: State, colors: dict[str, int]) -> None:
    height, width = screen.getmaxyx()

    if height < 16 or width < 38:
        draw_small_face(screen, state, colors)
        return

    blink = time.monotonic() < state.blink_until
    left_rows = eye_rows(state, blink)
    right_rows = eye_rows(state, blink)

    gap = 7
    eye_width = max(len(row) for row in left_rows)
    total_width = eye_width * 2 + gap
    start_x = max(0, (width - total_width) // 2)
    start_y = max(2, height // 2 - 5)

    for index, row in enumerate(left_rows):
        put_text(
            screen,
            start_y + index,
            start_x,
            row,
            colors["eye"] | curses.A_BOLD,
        )

    for index, row in enumerate(right_rows):
        put_text(
            screen,
            start_y + index,
            start_x + eye_width + gap,
            row,
            colors["eye"] | curses.A_BOLD,
        )

    mouth_y = start_y + 7

    if state.mood == "happy":
        mouth = "╰─────╯"
    elif state.mood == "surprised":
        mouth = "  ○  "
    elif state.mood == "sleepy":
        mouth = "  ~  "
    elif state.mood == "focused":
        mouth = " ─── "
    else:
        mouth = "╰───╯"

    centered(
        screen,
        mouth_y,
        mouth,
        colors["accent"] | curses.A_BOLD,
    )


def draw_status(screen: curses.window, state: State, colors: dict[str, int]) -> None:
    height, width = screen.getmaxyx()
    now = datetime.now()
    clock = now.strftime("%H:%M")
    date = now.strftime("%a %d %b")

    put_text(
        screen,
        1,
        2,
        f" {APP_NAME.upper()} ",
        colors["muted"] | curses.A_BOLD,
    )

    right = f"{clock}  {date}"
    put_text(
        screen,
        1,
        max(2, width - len(right) - 3),
        right,
        colors["text"],
    )

    status_parts: list[str] = []

    if state.battery.available and state.battery.percentage is not None:
        battery = f"BAT {state.battery.percentage}%"

        if state.battery.status:
            battery += f" {state.battery.status.lower()}"

        status_parts.append(battery)
    else:
        status_parts.append("BAT install Termux:API")

    if state.weather.available and state.weather.temperature is not None:
        status_parts.append(
            f"{state.weather.description} {round(state.weather.temperature)}°C"
        )
    else:
        status_parts.append("WEATHER press W")

    bottom_y = max(0, height - 4)

    centered(
        screen,
        bottom_y,
        "  •  ".join(status_parts),
        colors["muted"],
    )
    centered(
        screen,
        bottom_y + 1,
        state.message,
        colors["text"] | curses.A_BOLD,
    )
    centered(
        screen,
        bottom_y + 2,
        "SPACE react   B boop   W weather   S sleep   Q quit",
        colors["muted"],
    )


def set_mood(
    state: State,
    mood: str,
    duration: float = 3.0,
    message: str | None = None,
) -> None:
    state.mood = mood
    state.mood_until = time.monotonic() + duration

    if message is not None:
        state.message = message
    else:
        state.message = random.choice(MESSAGES.get(mood, MESSAGES["idle"]))


def refresh_battery(state: State) -> None:
    state.battery = get_battery()
    state.last_battery_check = time.monotonic()

    if not state.battery.available:
        return

    percent = state.battery.percentage
    status = state.battery.status.lower()

    if "charging" in status:
        set_mood(
            state,
            "happy",
            4.0,
            "charging. excellent life choices.",
        )
    elif percent is not None and percent <= 15:
        set_mood(
            state,
            "focused",
            4.0,
            "battery low. charger requested.",
        )


def refresh_weather(
    state: State,
    city: str | None,
    manual: bool = False,
) -> None:
    state.weather = fetch_weather(city)
    state.last_weather_check = time.monotonic()

    if state.weather.available:
        temp = state.weather.temperature or 0

        if state.weather.mood == "rainy":
            set_mood(
                state,
                "focused",
                4.0,
                random.choice(MESSAGES["rainy"]),
            )
        elif state.weather.mood == "stormy":
            set_mood(
                state,
                "surprised",
                4.0,
                "storm outside. staying alert.",
            )
        elif temp >= 34:
            set_mood(
                state,
                "sleepy",
                4.0,
                "too hot. efficiency has been cancelled.",
            )
        elif manual:
            set_mood(
                state,
                "happy",
                3.0,
                f"{state.weather.description.lower()}, {round(temp)} degrees",
            )
    elif manual:
        set_mood(
            state,
            "focused",
            4.0,
            "weather needs Termux:API location or a configured city",
        )


def init_colors() -> dict[str, int]:
    colors = {
        "eye": curses.A_BOLD,
        "accent": curses.A_BOLD,
        "text": curses.A_NORMAL,
        "muted": curses.A_DIM,
    }

    if not curses.has_colors():
        return colors

    curses.start_color()

    try:
        curses.use_default_colors()
    except curses.error:
        pass

    try:
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_MAGENTA, -1)
        curses.init_pair(3, curses.COLOR_WHITE, -1)
        curses.init_pair(4, curses.COLOR_BLUE, -1)

        colors["eye"] = curses.color_pair(1) | curses.A_BOLD
        colors["accent"] = curses.color_pair(2) | curses.A_BOLD
        colors["text"] = curses.color_pair(3)
        colors["muted"] = curses.color_pair(4) | curses.A_BOLD
    except curses.error:
        pass

    return colors


def main_loop(screen: curses.window, city: str | None) -> None:
    try:
        curses.curs_set(0)
    except curses.error:
        pass

    screen.nodelay(True)
    screen.keypad(True)
    screen.timeout(50)

    colors = init_colors()

    state = State(
        next_blink=time.monotonic() + random.uniform(1.5, 4.0),
        next_gaze=time.monotonic() + random.uniform(0.7, 2.0),
        next_message=time.monotonic() + random.uniform(8.0, 15.0),
    )

    refresh_battery(state)
    refresh_weather(state, city)

    while True:
        now_mono = time.monotonic()
        now_hour = datetime.now().hour

        if now_mono >= state.next_blink:
            state.blink_until = now_mono + random.uniform(0.10, 0.18)
            state.next_blink = now_mono + random.uniform(2.0, 5.5)

        if now_mono >= state.next_gaze:
            state.gaze_x = random.choice([-2, -1, 0, 0, 0, 1, 2])
            state.gaze_y = random.choice([-1, 0, 0, 0, 1])
            state.next_gaze = now_mono + random.uniform(1.0, 3.2)

        if state.mood != "idle" and now_mono >= state.mood_until:
            state.mood = "idle"

        if state.mood == "idle" and (now_hour >= 23 or now_hour < 7):
            state.mood = "sleepy"

        if now_mono >= state.next_message and state.mood in {"idle", "sleepy"}:
            pool = (
                MESSAGES["sleepy"]
                if state.mood == "sleepy"
                else MESSAGES["idle"]
            )
            state.message = random.choice(pool)
            state.next_message = now_mono + random.uniform(10.0, 18.0)

        if now_mono - state.last_battery_check >= 30:
            refresh_battery(state)

        if now_mono - state.last_weather_check >= 600:
            refresh_weather(state, city)

        screen.erase()
        draw_face(screen, state, colors)
        draw_status(screen, state, colors)
        screen.refresh()

        key = screen.getch()

        if key == -1:
            continue

        if key in (ord("q"), ord("Q")):
            break

        if key in (ord("b"), ord("B")):
            set_mood(
                state,
                "happy",
                3.2,
                random.choice(MESSAGES["happy"]),
            )
        elif key in (ord("w"), ord("W")):
            state.message = "checking weather..."
            screen.refresh()
            refresh_weather(state, city, manual=True)
        elif key in (ord("s"), ord("S")):
            set_mood(
                state,
                "sleepy",
                8.0,
                random.choice(MESSAGES["sleepy"]),
            )
        elif key == ord(" "):
            set_mood(
                state,
                random.choice(["happy", "surprised", "focused"]),
                3.0,
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Full-screen Desk Buddy for Termux."
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
        curses.wrapper(main_loop, city)
    except KeyboardInterrupt:
        pass
    finally:
        print("Desk Buddy is sleeping.")


if __name__ == "__main__":
    main()
