#!/usr/bin/env python3
from __future__ import annotations

import re
import time
from pathlib import Path


DEFAULT_FRAME_SECONDS = 0.064
DEFAULT_TOTAL_FRAMES = 102

WHITE = (245, 255, 255, 255)
BLACK = (0, 0, 0, 255)


class OledAssetShow:
    """Play a user-local 128x64 Arduino bitmap animation.

    The repo intentionally does not embed the user's bitmap payload. Instead,
    this loader discovers animation_frames.h from the project or Downloads,
    parses the original pointer order, and plays those local frames directly.
    """

    def __init__(self) -> None:
        self.active = False
        self.started = 0.0
        self.frames: list[bytes] = []
        self.frame_seconds = DEFAULT_FRAME_SECONDS
        self.total_frames = DEFAULT_TOTAL_FRAMES
        self.source_path: Path | None = None
        self.loaded = False
        self.load_error = ""

    def _candidate_headers(self) -> list[Path]:
        home = Path.home()
        cwd = Path.cwd()

        candidates = [
            cwd / "animation_frames.h",
            cwd / "animation_frames(1).h",
            home / "desk-buddy" / "animation_frames.h",
            home / "desk-buddy" / "animation_frames(1).h",
            home / "storage" / "downloads" / "animation_frames.h",
            home / "storage" / "downloads" / "animation_frames(1).h",
            Path("/sdcard/Download/animation_frames.h"),
            Path("/sdcard/Download/animation_frames(1).h"),
            Path("/storage/emulated/0/Download/animation_frames.h"),
            Path("/storage/emulated/0/Download/animation_frames(1).h"),
        ]

        seen: set[str] = set()
        output: list[Path] = []

        for path in candidates:
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            output.append(path)

        return output

    def _candidate_sketches(self) -> list[Path]:
        home = Path.home()
        cwd = Path.cwd()

        return [
            cwd / "loveMeNotOledLyrics.ino",
            cwd / "loveMeNotOledLyrics(1).ino",
            home / "desk-buddy" / "loveMeNotOledLyrics.ino",
            home / "desk-buddy" / "loveMeNotOledLyrics(1).ino",
            home / "storage" / "downloads" / "loveMeNotOledLyrics.ino",
            home / "storage" / "downloads" / "loveMeNotOledLyrics(1).ino",
            Path("/sdcard/Download/loveMeNotOledLyrics.ino"),
            Path("/sdcard/Download/loveMeNotOledLyrics(1).ino"),
            Path("/storage/emulated/0/Download/loveMeNotOledLyrics.ino"),
            Path("/storage/emulated/0/Download/loveMeNotOledLyrics(1).ino"),
        ]

    def _find_readable(self, paths: list[Path]) -> Path | None:
        for path in paths:
            try:
                if path.is_file() and path.stat().st_size > 0:
                    return path
            except OSError:
                continue
        return None

    def ensure_loaded(self) -> bool:
        if self.loaded and self.frames:
            return True

        self.loaded = True
        self.frames = []
        self.load_error = ""

        header_path = self._find_readable(
            self._candidate_headers()
        )

        if header_path is None:
            self.load_error = (
                "animation_frames.h not found in project or Downloads"
            )
            return False

        try:
            text = header_path.read_text(
                errors="replace",
            )
        except OSError as exc:
            self.load_error = f"Could not read frame header: {exc}"
            return False

        array_pattern = re.compile(
            r"const\s+unsigned\s+char\s+"
            r"(epd_bitmap_frame_\d+_delay_\d+)\[\]\s+"
            r"PROGMEM\s*=\s*\{(.*?)\};",
            re.S,
        )

        arrays: dict[str, bytes] = {}

        for match in array_pattern.finditer(text):
            name = match.group(1)
            values = re.findall(
                r"0x([0-9a-fA-F]{2})",
                match.group(2),
            )

            try:
                payload = bytes(
                    int(value, 16)
                    for value in values
                )
            except ValueError:
                continue

            if len(payload) == 1024:
                arrays[name] = payload

        order_match = re.search(
            r"const\s+unsigned\s+char\s*\*\s*"
            r"epd_bitmap_allArray\[\d+\]\s*=\s*"
            r"\{(.*?)\};",
            text,
            re.S,
        )

        if order_match is None:
            self.load_error = "epd_bitmap_allArray was not found"
            return False

        order = re.findall(
            r"epd_bitmap_frame_\d+_delay_\d+",
            order_match.group(1),
        )

        frames = [
            arrays[name]
            for name in order
            if name in arrays
        ]

        if not frames:
            self.load_error = "No valid 128x64 frames were parsed"
            return False

        self.frames = frames
        self.total_frames = len(frames)
        self.source_path = header_path

        sketch = self._find_readable(
            self._candidate_sketches()
        )

        if sketch is not None:
            try:
                sketch_text = sketch.read_text(
                    errors="replace",
                )

                delay_match = re.search(
                    r"ANIMATION_DELAY_MS\s*=\s*(\d+)",
                    sketch_text,
                )
                total_match = re.search(
                    r"TOTAL_FRAMES\s*=\s*(\d+)",
                    sketch_text,
                )

                if delay_match:
                    delay_ms = max(
                        10,
                        min(1000, int(delay_match.group(1))),
                    )
                    self.frame_seconds = delay_ms / 1000.0

                if total_match:
                    requested = int(total_match.group(1))
                    self.total_frames = min(
                        len(self.frames),
                        max(1, requested),
                    )
            except (OSError, ValueError):
                pass

        return True

    def start(self) -> bool:
        if not self.ensure_loaded():
            return False

        self.active = True
        self.started = time.monotonic()
        return True

    def stop(self) -> None:
        self.active = False

    def frame_index(self, now: float) -> int:
        if not self.active:
            return -1

        return int(
            (now - self.started)
            / max(0.010, self.frame_seconds)
        )

    def draw(self, canvas, now: float) -> bool:
        frame_index = self.frame_index(now)

        if frame_index < 0:
            return False

        if frame_index >= self.total_frames:
            self.active = False
            return False

        frame = self.frames[frame_index]

        canvas.clear()

        scale = min(
            canvas.width / 128.0,
            canvas.height / 64.0,
        )

        panel_w = 128.0 * scale
        panel_h = 64.0 * scale

        origin_x = (canvas.width - panel_w) / 2.0
        origin_y = (canvas.height - panel_h) / 2.0

        # Original Arduino drawBitmap semantics: 1 bits are lit pixels.
        # We preserve the exact 128x64 bitmap geometry and pointer order.
        for source_y in range(64):
            row_offset = source_y * 16
            run_start: int | None = None

            for source_x in range(128):
                byte = frame[
                    row_offset
                    + source_x // 8
                ]
                mask = 0x80 >> (source_x % 8)
                lit = bool(byte & mask)

                if lit and run_start is None:
                    run_start = source_x

                if (
                    run_start is not None
                    and (
                        not lit
                        or source_x == 127
                    )
                ):
                    run_end = (
                        source_x + 1
                        if lit and source_x == 127
                        else source_x
                    )

                    canvas.rect(
                        origin_x + run_start * scale,
                        origin_y + source_y * scale,
                        max(
                            1.0,
                            (run_end - run_start) * scale,
                        ),
                        max(1.0, scale),
                        WHITE,
                    )

                    run_start = None

        return True

    def source_label(self) -> str:
        if self.source_path is None:
            return ""
        return self.source_path.name
