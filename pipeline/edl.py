"""edl.json: schemat (sekcja 6.2), walidacja, zapis atomowy, plan --auto."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pipeline import config


def edl_path(project: Path) -> Path:
    return config.edit_dir(project) / "edl.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_edl(project: Path) -> dict:
    return json.loads(edl_path(project).read_text())


def validate_edl(edl: dict, media: dict | None = None) -> list[str]:
    """Reguły z sekcji 6.2. Zwraca listę błędów (pusta = OK)."""
    errors: list[str] = []
    if not isinstance(edl, dict):
        return ["edl musi być obiektem JSON"]
    if edl.get("version") != 2:
        errors.append("version: wymagane 2")
    sources = edl.get("sources")
    if not isinstance(sources, dict) or not sources:
        errors.append("sources: wymagany niepusty obiekt {alias: plik}")
        sources = {}
    for alias, rel in sources.items():
        if not isinstance(rel, str) or rel.startswith("/") or ".." in Path(rel).parts:
            errors.append(f"sources.{alias}: ścieżka musi być względna wobec folderu projektu")
    ranges = edl.get("ranges")
    if not isinstance(ranges, list):
        errors.append("ranges: wymagana lista")
        ranges = []
    ids = []
    for i, r in enumerate(ranges):
        where = f"ranges[{i}]"
        if not isinstance(r, dict):
            errors.append(f"{where}: musi być obiektem")
            continue
        rid = r.get("id")
        if not rid or not isinstance(rid, str):
            errors.append(f"{where}: brak id")
        elif rid in ids:
            errors.append(f"{where}: zduplikowane id {rid!r}")
        else:
            ids.append(rid)
        src = r.get("source")
        if src not in sources:
            errors.append(f"{where}: source {src!r} nie występuje w sources")
        start, end = r.get("start"), r.get("end")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            errors.append(f"{where}: start/end muszą być liczbami")
        elif start >= end:
            errors.append(f"{where}: wymagane start < end (start={start}, end={end})")
        elif start < 0:
            errors.append(f"{where}: start < 0")
        elif media is not None and src in sources:
            stem = Path(sources[src]).stem
            info = media.get("sources", {}).get(stem)
            if info and end > info["duration"] + 0.001:
                errors.append(
                    f"{where}: end={end} poza trwaniem źródła {src} ({info['duration']:.3f}s)"
                )
        crop_x = r.get("crop_x", 0.5)
        if not isinstance(crop_x, (int, float)) or not (0.0 <= crop_x <= 1.0):
            errors.append(f"{where}: crop_x poza zakresem [0,1]")
        for flag in ("subtitles", "mute", "locked"):
            if flag in r and not isinstance(r[flag], bool):
                errors.append(f"{where}: {flag} musi być bool")
    order = edl.get("order")
    if not isinstance(order, list):
        errors.append("order: wymagana lista")
    else:
        unknown = [o for o in order if o not in ids]
        if unknown:
            errors.append(f"order: nieznane id: {unknown}")
        seen = set()
        for o in order:
            if o in seen:
                errors.append(f"order: zduplikowane id {o!r}")
            seen.add(o)
    if "approved" in edl and not isinstance(edl["approved"], bool):
        errors.append("approved: musi być bool")
    return errors


def save_edl(project: Path, edl: dict, created_by: str = "agent") -> dict:
    """Walidacja + zapis atomowy (.tmp + rename); aktualizuje meta.updated_at."""
    from pipeline import probe

    media = probe.load_media(project)
    errors = validate_edl(edl, media if media["sources"] else None)
    if errors:
        raise ValueError("edl.json niepoprawny: " + "; ".join(errors))
    meta = edl.setdefault("meta", {})
    meta.setdefault("created_by", created_by)
    meta["updated_at"] = now_iso()
    path = edl_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(edl, indent=2, ensure_ascii=False))
    tmp.rename(path)
    return edl


def check_project(project: Path) -> list[str]:
    path = edl_path(project)
    if not path.exists():
        return [f"brak pliku {path}"]
    try:
        edl = load_edl(project)
    except json.JSONDecodeError as e:
        return [f"niepoprawny JSON: {e}"]
    from pipeline import probe

    media = probe.load_media(project)
    return validate_edl(edl, media if media["sources"] else None)


def plan_auto(project: Path) -> Path:
    """Naiwny plan: wszystkie segmenty mowy po kolei (D-004), z paddingiem z preferences."""
    from pipeline import probe, transcribe

    prefs = config.load_preferences(project)
    media = probe.load_media(project)
    if not media["sources"]:
        raise RuntimeError("Brak media.json — uruchom najpierw `kadr transcribe` (albo `kadr probe`).")
    transcripts = transcribe.load_transcripts(project)
    pad_before = prefs["pacing"]["pad_before_ms"] / 1000.0
    pad_after = prefs["pacing"]["pad_after_ms"] / 1000.0
    sub_default = bool(prefs["subtitles"]["default"])

    ranges = []
    n = 0
    for stem, info in media["sources"].items():
        t = transcripts.get(stem)
        segs = t["segments"] if t and t.get("segments") else None
        if segs:
            for seg in segs:
                n += 1
                ranges.append({
                    "id": f"r{n}",
                    "source": stem,
                    "start": round(max(0.0, seg["start"] - pad_before), 3),
                    "end": round(min(info["duration"], seg["end"] + pad_after), 3),
                    "beat": "",
                    "quote": seg["text"],
                    "subtitles": sub_default,
                    "crop_x": 0.5,
                    "mute": False,
                    "locked": False,
                    "note": "",
                })
        else:
            n += 1
            ranges.append({
                "id": f"r{n}",
                "source": stem,
                "start": 0.0,
                "end": round(info["duration"], 3),
                "beat": "",
                "quote": "",
                "subtitles": sub_default,
                "crop_x": 0.5,
                "mute": False,
                "locked": False,
                "note": "brak transkryptu — cały klip",
            })
    edl = {
        "version": 2,
        "project": Path(project).name,
        "sources": {stem: info["file"] for stem, info in media["sources"].items()},
        "ranges": ranges,
        "order": [r["id"] for r in ranges],
        "approved": False,
        "meta": {"created_by": "agent", "updated_at": now_iso()},
    }
    save_edl(project, edl, created_by="agent")
    return edl_path(project)
