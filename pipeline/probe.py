"""ffprobe źródeł → edit/media.json (rozdzielczości, czasy, fps, sha256)."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from pipeline import config


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ffprobe_streams(path: Path) -> dict:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", str(path),
        ],
        capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(out)


def _parse_fps(rate: str) -> float:
    num, _, den = rate.partition("/")
    den = den or "1"
    return float(num) / float(den) if float(den) else 0.0


def probe_source(path: Path) -> dict:
    info = ffprobe_streams(path)
    video = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    if video is None:
        raise ValueError(f"{path.name}: brak strumienia wideo")
    return {
        "file": path.name,
        "sha256": sha256_file(path),
        "duration": float(info["format"]["duration"]),
        "width": int(video["width"]),
        "height": int(video["height"]),
        "fps": round(_parse_fps(video.get("r_frame_rate", "30/1")), 3),
        "has_audio": audio is not None,
    }


def media_path(project: Path) -> Path:
    return config.edit_dir(project) / "media.json"


def load_media(project: Path) -> dict:
    path = media_path(project)
    if path.exists():
        return json.loads(path.read_text())
    return {"sources": {}}


def probe_project(project: Path, sources: list[Path]) -> dict:
    """Probe wszystkich źródeł; hash liczony ponownie tylko przy zmianie mtime/size."""
    prev = load_media(project)
    media = {"sources": {}}
    for src in sources:
        stem = src.stem
        stat = src.stat()
        old = prev["sources"].get(stem)
        if old and old.get("_mtime") == stat.st_mtime_ns and old.get("_size") == stat.st_size:
            media["sources"][stem] = old
            continue
        entry = probe_source(src)
        entry["_mtime"] = stat.st_mtime_ns
        entry["_size"] = stat.st_size
        media["sources"][stem] = entry
    path = media_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(media, indent=2, ensure_ascii=False))
    tmp.rename(path)
    return media
