#!/usr/bin/env python3
"""Desk Buddy local server for Termux.

Serves the animated web UI and a few tiny device/network APIs.
No third-party Python packages are required.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import shutil
import subprocess
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
WEATHER_TTL_SECONDS = 300
WEATHER_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def read_termux_battery() -> dict[str, Any]:
    command = shutil.which("termux-battery-status")
    if not command:
        return {
            "available": False,
            "reason": "termux-api-command-missing",
            "message": "Install the Termux:API app and run: pkg install termux-api",
        }

    try:
        result = subprocess.run(
            [command],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "available": False,
            "reason": "termux-api-failed",
            "message": str(exc),
        }

    if result.returncode != 0:
        return {
            "available": False,
            "reason": "termux-api-error",
            "message": (result.stderr or result.stdout or "Battery query failed").strip(),
        }

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
            "available": False,
            "reason": "invalid-battery-json",
            "message": "Termux:API returned unreadable battery data.",
        }

    return {"available": True, **data}


def fetch_weather(lat: float, lon: float) -> dict[str, Any]:
    cache_key = f"{lat:.3f},{lon:.3f}"
    now = time.time()
    cached = WEATHER_CACHE.get(cache_key)
    if cached and now - cached[0] < WEATHER_TTL_SECONDS:
        return {**cached[1], "cached": True}

    params = urlencode(
        {
            "latitude": f"{lat:.5f}",
            "longitude": f"{lon:.5f}",
            "current": (
                "temperature_2m,apparent_temperature,is_day,precipitation,"
                "rain,showers,snowfall,weather_code,cloud_cover,wind_speed_10m"
            ),
            "timezone": "auto",
        }
    )
    url = f"https://api.open-meteo.com/v1/forecast?{params}"
    request = Request(url, headers={"User-Agent": "desk-buddy/0.1"})

    try:
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Weather service unavailable: {exc}") from exc

    result = {
        "cached": False,
        "latitude": payload.get("latitude"),
        "longitude": payload.get("longitude"),
        "timezone": payload.get("timezone"),
        "current": payload.get("current", {}),
        "current_units": payload.get("current_units", {}),
    }
    WEATHER_CACHE[cache_key] = (now, result)
    return result


class DeskBuddyHandler(BaseHTTPRequestHandler):
    server_version = "DeskBuddy/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[desk-buddy] {self.address_string()} - {fmt % args}")

    def send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json_bytes(payload)
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def send_static(self, request_path: str) -> None:
        relative = request_path.lstrip("/") or "index.html"
        candidate = (WEB_ROOT / relative).resolve()

        try:
            candidate.relative_to(WEB_ROOT.resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN.value, "Forbidden")
            return

        if candidate.is_dir():
            candidate = candidate / "index.html"

        if not candidate.exists() or not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND.value, "Not found")
            return

        content = candidate.read_bytes()
        mime, _ = mimetypes.guess_type(candidate.name)
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", f"{mime or 'application/octet-stream'}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/health":
            self.send_json(
                {
                    "ok": True,
                    "name": "Desk Buddy",
                    "version": "0.1.0",
                    "time": int(time.time()),
                }
            )
            return

        if parsed.path == "/api/battery":
            self.send_json(read_termux_battery())
            return

        if parsed.path == "/api/weather":
            query = parse_qs(parsed.query)
            try:
                lat = float(query["lat"][0])
                lon = float(query["lon"][0])
            except (KeyError, IndexError, TypeError, ValueError):
                self.send_json(
                    {"error": "lat and lon query parameters are required"},
                    HTTPStatus.BAD_REQUEST,
                )
                return

            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                self.send_json(
                    {"error": "Invalid latitude or longitude"},
                    HTTPStatus.BAD_REQUEST,
                )
                return

            try:
                weather = fetch_weather(lat, lon)
            except RuntimeError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
                return

            self.send_json(weather)
            return

        self.send_static(parsed.path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Desk Buddy on your phone.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not WEB_ROOT.exists():
        raise SystemExit(f"Missing web directory: {WEB_ROOT}")

    server = ThreadingHTTPServer((args.host, args.port), DeskBuddyHandler)
    print(f"Desk Buddy is awake at http://{args.host}:{args.port}")
    print("Press Ctrl+C to put it back to sleep.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDesk Buddy is going to sleep.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
