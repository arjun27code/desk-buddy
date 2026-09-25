#!/usr/bin/env python3
from __future__ import annotations

import math
import shutil
import struct
import subprocess
import threading
import time
import wave
import zlib
from pathlib import Path


class GibberVoice:
    """Caption-first robotic data-sound voice.

    The audible layer is a compact FSK-style modem chirp. The human-readable
    message remains in the caption overlay. This is intentionally local and
    offline and does not claim wire compatibility with ggwave/GibberLink.
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.caption_text = ""
        self.caption_until = 0.0

        self.last_spoken_at = 0.0
        self.last_text = ""
        self.counter = 0

        self.player_available = shutil.which("termux-media-player") is not None

        self.cache_dir = Path.home() / ".cache" / "desk-buddy" / "gibber"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def caption(self) -> str:
        with self.lock:
            if time.monotonic() > self.caption_until:
                return ""
            return self.caption_text

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

        if not force and now - self.last_spoken_at < 1.8:
            return

        if not force and cleaned == self.last_text and now - self.last_spoken_at < 12.0:
            return

        self.last_spoken_at = now
        self.last_text = cleaned
        self.counter += 1

        path = self.cache_dir / f"gibber_{self.counter % 4}.wav"

        try:
            self._write_wave(
                cleaned,
                path,
                rate=rate,
                pitch=pitch,
            )
        except Exception:
            return

        if not self.player_available:
            return

        try:
            subprocess.Popen(
                ["termux-media-player", "play", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except OSError:
            self.player_available = False

    def _write_wave(
        self,
        text: str,
        path: Path,
        *,
        rate: float = 1.0,
        pitch: float = 1.0,
    ) -> None:
        sample_rate = 22050
        slot = max(0.012, min(0.035, 0.021 / max(0.70, rate)))

        # Limit the sound packet so a long caption does not become a ten-second
        # dial-up solo. A CRC still makes each phrase sound distinct.
        data = text.encode("utf-8")[:64]
        crc = zlib.crc32(data).to_bytes(4, "big")
        payload = b"\xAA\x55" + data + crc

        tones: list[tuple[float, float]] = []

        base_shift = clamp_pitch(pitch)
        for frequency in (760, 1020, 1360, 1760):
            tones.append((frequency * base_shift, slot * 0.72))

        for byte in payload:
            high = (byte >> 4) & 0x0F
            low = byte & 0x0F

            tones.append(((900 + high * 92) * base_shift, slot))
            tones.append(((900 + low * 92) * base_shift, slot))

        samples: list[int] = []
        phase = 0.0

        for frequency, duration in tones:
            count = max(1, int(sample_rate * duration))

            for index in range(count):
                # Smooth envelope removes clicks between modem symbols.
                envelope = math.sin(math.pi * (index + 0.5) / count) ** 0.60
                phase += 2.0 * math.pi * frequency / sample_rate

                fundamental = math.sin(phase)
                subharmonic = math.sin(phase * 0.50)

                sample = int(
                    10800 * envelope * fundamental
                    + 2100 * envelope * subharmonic
                )
                samples.append(max(-32767, min(32767, sample)))

        path.parent.mkdir(parents=True, exist_ok=True)

        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            output.writeframes(
                struct.pack(
                    f"<{len(samples)}h",
                    *samples,
                )
            )


def clamp_pitch(value: float) -> float:
    return max(0.78, min(1.32, float(value)))
