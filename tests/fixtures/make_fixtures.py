#!/usr/bin/env python3
"""Generuje 2 syntetyczne klipy testowe (testsrc2 + ton sinus, 1280x720, 30 fps).

Klipy nie są commitowane (D-002) — wołane z tests/conftest.py albo ręcznie:
    python tests/fixtures/make_fixtures.py [katalog_docelowy]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CLIPS = {
    # nazwa: (czas trwania s, częstotliwość tonu Hz)
    "clip_a": (6.0, 440),
    "clip_b": (4.0, 660),
}


def make_fixtures(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, (dur, freq) in CLIPS.items():
        out = out_dir / f"{name}.mp4"
        if not out.exists():
            subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", f"testsrc2=size=1280x720:rate=30:duration={dur}",
                    "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={dur}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(out),
                ],
                check=True,
            )
        paths.append(out)
    return paths


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
    for p in make_fixtures(target):
        print(p)
