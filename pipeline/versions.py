"""Wersjonowanie renderów: edit/versions/vNNN/ + manifest.json (sekcja 6.4)."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from pipeline import config


def versions_dir(project: Path) -> Path:
    return config.edit_dir(project) / "versions"


def list_versions(project: Path) -> list[str]:
    vdir = versions_dir(project)
    if not vdir.is_dir():
        return []
    return sorted(p.name for p in vdir.iterdir() if re.fullmatch(r"v\d{3}", p.name))


def next_version(project: Path) -> str:
    existing = list_versions(project)
    n = int(existing[-1][1:]) + 1 if existing else 1
    return f"v{n:03d}"


def create_version(project: Path) -> Path:
    vdir = versions_dir(project) / next_version(project)
    vdir.mkdir(parents=True)
    return vdir


def write_manifest(
    vdir: Path, formats: list[str], durations: dict, note: str = "", proxy: bool = False
) -> dict:
    edl_copy = vdir / "edl.json"
    edl_sha = hashlib.sha256(edl_copy.read_bytes()).hexdigest() if edl_copy.exists() else ""
    manifest = {
        "version": vdir.name,
        "rendered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "formats": formats,
        "edl_sha256": edl_sha,
        "durations_s": durations,
        "note": note,
        "proxy": proxy,
    }
    (vdir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest


def snapshot_edl(project: Path, vdir: Path) -> None:
    from pipeline import edl as edl_mod

    shutil.copy2(edl_mod.edl_path(project), vdir / "edl.json")
