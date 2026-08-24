"""edl + transkrypty → master.ass w osi czasu WYJŚCIA, tylko zakresy subtitles: true."""
from __future__ import annotations

import platform
import re
import subprocess
from pathlib import Path

# PlayRes per format (krótszy bok 1080)
PLAYRES = {"9x16": (1080, 1920), "16x9": (1920, 1080), "1x1": (1080, 1080)}
REF_PLAYRES_Y = 1920  # font_size z preferences odnosi się do PlayResY=1920 (9x16)


def list_system_fonts() -> list[str]:
    """Rodziny fontów (fc-list; fallback macOS: system_profiler)."""
    names: set[str] = set()
    try:
        out = subprocess.run(
            ["fc-list", "--format", "%{family}\t%{style}\n"],
            capture_output=True, text=True, check=True,
        ).stdout
        for line in out.splitlines():
            family, _, style = line.partition("\t")
            for fam in family.split(","):
                fam = fam.strip()
                if not fam:
                    continue
                names.add(fam)
                for st in style.split(","):
                    st = st.strip()
                    if st:
                        names.add(f"{fam} {st}")
    except (FileNotFoundError, subprocess.CalledProcessError):
        if platform.system() == "Darwin":
            out = subprocess.run(
                ["system_profiler", "SPFontsDataType"], capture_output=True, text=True
            ).stdout
            for m in re.finditer(r"Family:\s*(.+)", out):
                names.add(m.group(1).strip())
    return sorted(names)


def validate_font(family: str) -> None:
    fonts = list_system_fonts()
    if family.lower() not in {f.lower() for f in fonts}:
        preview = ", ".join(fonts[:40])
        raise RuntimeError(
            f"Font {family!r} nie jest zainstalowany w systemie. Dostępne m.in.: {preview}"
        )


def hex_to_ass(color: str) -> str:
    """#RRGGBB → &H00BBGGRR (ASS: AABBGGRR, alpha 00 = kryjący)."""
    c = color.lstrip("#")
    r, g, b = c[0:2], c[2:4], c[4:6]
    return f"&H00{b}{g}{r}".upper()


def ass_time(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def words_in_range(transcript: dict, start: float, end: float) -> list[dict]:
    eps = 0.02
    return [
        w for w in transcript.get("words", [])
        if w["start"] >= start - eps and w["end"] <= end + eps
    ]


def chunk_words(words: list[dict], n: int) -> list[list[dict]]:
    return [words[i:i + n] for i in range(0, len(words), n)]


def build_events(edl: dict, transcripts: dict, chunk_size: int, upper: bool) -> list[dict]:
    """Zdarzenia napisów w osi czasu wyjścia: [{start, end, text}] (offsety jak video-use Rule 5)."""
    ranges = {r["id"]: r for r in edl["ranges"]}
    events = []
    offset = 0.0
    for rid in edl["order"]:
        r = ranges[rid]
        dur = r["end"] - r["start"]
        if r.get("subtitles"):
            stem = Path(edl["sources"][r["source"]]).stem
            transcript = transcripts.get(stem)
            if transcript:
                for chunk in chunk_words(words_in_range(transcript, r["start"], r["end"]), chunk_size):
                    text = " ".join(w["text"] for w in chunk)
                    if upper:
                        text = text.upper()
                    ev_start = offset + max(0.0, chunk[0]["start"] - r["start"])
                    ev_end = offset + min(dur, chunk[-1]["end"] - r["start"])
                    if ev_end > ev_start:
                        events.append({"start": ev_start, "end": ev_end, "text": text})
        offset += dur
    return events


def build_ass(edl: dict, transcripts: dict, prefs: dict, fmt: str) -> str:
    sub = prefs["subtitles"]
    play_x, play_y = PLAYRES[fmt]
    font_size = round(sub["font_size"] * play_y / REF_PLAYRES_Y, 1)
    margin_v = round(sub["margin_v"] * play_y / REF_PLAYRES_Y)
    events = build_events(edl, transcripts, int(sub["chunk_words"]), sub["case"] == "upper")
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {play_x}",
        f"PlayResY: {play_y}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, "
        "Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{sub['font_family']},{font_size},{hex_to_ass(sub['primary_color'])},"
        f"{hex_to_ass(sub['outline_color'])},&H00000000,0,0,1,{sub['outline']},0,2,40,40,{margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for ev in events:
        text = ev["text"].replace("\n", " ")
        lines.append(
            f"Dialogue: 0,{ass_time(ev['start'])},{ass_time(ev['end'])},Default,,0,0,0,,{text}"
        )
    return "\n".join(lines) + "\n"


def has_subtitles(edl: dict) -> bool:
    ranges = {r["id"]: r for r in edl["ranges"]}
    return any(ranges[rid].get("subtitles") for rid in edl["order"])
