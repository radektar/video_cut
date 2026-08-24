"""Źródła → edit/proxy/<stem>.mp4 (540p, H.264 CRF 30, faststart; cache po sha256)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from pipeline import config


def proxy_dir(project: Path) -> Path:
    return config.edit_dir(project) / "proxy"


def _cache_path(project: Path) -> Path:
    return proxy_dir(project) / ".cache.json"


def build_proxy(src: Path, out: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
            "-vf", "scale=-2:540",
            "-c:v", "libx264", "-crf", "30", "-preset", "veryfast",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-c:a", "aac", "-b:a", "96k",
            str(out),
        ],
        check=True,
    )


def proxy_project(project: Path, media: dict) -> dict:
    pdir = proxy_dir(project)
    pdir.mkdir(parents=True, exist_ok=True)
    cache_file = _cache_path(project)
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    built = 0
    cached = 0
    for stem, entry in media["sources"].items():
        out = pdir / f"{stem}.mp4"
        if out.exists() and cache.get(stem) == entry["sha256"]:
            cached += 1
            continue
        build_proxy(Path(project) / entry["file"], out)
        cache[stem] = entry["sha256"]
        built += 1
    cache_file.write_text(json.dumps(cache, indent=2))
    return {"built": built, "cached": cached}
