"""Preferencje projektu: domyślne wartości, wczytywanie i zapis (sekcja 6.1 spec)."""
from __future__ import annotations

import copy
import os
from pathlib import Path

import yaml

DEFAULT_PREFERENCES: dict = {
    "version": 1,
    "output": {
        "formats": ["9x16"],
        "resolution": 1080,
        "fps": "source",
    },
    "subtitles": {
        "default": False,
        "font_family": "Menlo Bold",
        "font_size": 20,
        "case": "natural",
        "chunk_words": 3,
        "margin_v": 70,
        "primary_color": "#FFFFFF",
        "outline_color": "#000000",
        "outline": 2,
    },
    "crop": {"mode": "manual"},
    "pacing": {"pad_before_ms": 50, "pad_after_ms": 80},
    "audio": {"loudnorm": True, "fade_ms": 30},
    "grade": "none",
    "language": "pl",
    "whisper": {"model": "large-v3-turbo", "binary": "auto"},
}

ALLOWED_FORMATS = ("9x16", "16x9", "1x1")

def kadr_home() -> Path:
    return Path(os.environ.get("KADR_HOME", Path.home() / ".kadr"))


def edit_dir(project: Path) -> Path:
    return Path(project) / "edit"


def preferences_path(project: Path) -> Path:
    return edit_dir(project) / "preferences.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_preferences(project: Path) -> dict:
    """Preferencje projektu nałożone na domyślne (brakujące klucze uzupełniane)."""
    path = preferences_path(project)
    if path.exists():
        data = yaml.safe_load(path.read_text()) or {}
    else:
        data = {}
    return _deep_merge(DEFAULT_PREFERENCES, data)


def validate_preferences(prefs: dict) -> list[str]:
    errors = []
    fmts = prefs.get("output", {}).get("formats", [])
    if not isinstance(fmts, list) or not fmts:
        errors.append("output.formats: wymagana niepusta lista")
    else:
        for f in fmts:
            if f not in ALLOWED_FORMATS:
                errors.append(f"output.formats: niedozwolony format {f!r} (dozwolone: {ALLOWED_FORMATS})")
    fps = prefs.get("output", {}).get("fps", "source")
    if fps not in ("source", 24, 30):
        errors.append("output.fps: dozwolone source | 24 | 30")
    case = prefs.get("subtitles", {}).get("case", "natural")
    if case not in ("natural", "upper"):
        errors.append("subtitles.case: dozwolone natural | upper")
    cw = prefs.get("subtitles", {}).get("chunk_words", 3)
    if not isinstance(cw, int) or cw < 1:
        errors.append("subtitles.chunk_words: wymagana liczba całkowita >= 1")
    return errors


def save_preferences(project: Path, prefs: dict) -> None:
    errors = validate_preferences(prefs)
    if errors:
        raise ValueError("; ".join(errors))
    path = preferences_path(project)
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(prefs, allow_unicode=True, sort_keys=False))
    tmp.rename(path)


def write_default_preferences(project: Path) -> Path:
    """Przy `kadr init`: kopiuje ~/.kadr/preferences.yaml, a gdy brak — domyślne."""
    path = preferences_path(project)
    global_prefs = kadr_home() / "preferences.yaml"
    if global_prefs.exists():
        path.write_text(global_prefs.read_text())
    else:
        path.write_text(yaml.safe_dump(DEFAULT_PREFERENCES, allow_unicode=True, sort_keys=False))
    return path
