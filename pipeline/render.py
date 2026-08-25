"""Render edl.json → mp4 per format (adaptacja video-use render.py, sekcja 8).

Reguły produkcyjne: ekstrakcja per segment → concat -c copy → finalny przebieg
(grade → napisy NA KOŃCU łańcucha + loudnorm). Wynik zawsze do versions/vNNN/.
"""
from __future__ import annotations

import functools
import subprocess
import tempfile
import time
from pathlib import Path

from pipeline import config, edl as edl_mod, probe, subtitles, transcribe, versions

# format → (crop wyrażenie z {crop_x}, szerokość:wysokość przy krótszym boku S)
FORMAT_SPECS = {
    "9x16": ("crop=ih*9/16:ih:(iw-ih*9/16)*{crop_x}:0", lambda s: (s, s * 16 // 9)),
    "16x9": (None, lambda s: (s * 16 // 9, s)),
    "1x1": ("crop=ih:ih:(iw-ih)*{crop_x}:0", lambda s: (s, s)),
}

GRADES = {
    "none": None,
    "neutral_punch": "eq=contrast=1.06:saturation=1.12",
    "warm_cinematic": "colorbalance=rm=0.06:bm=-0.06,eq=contrast=1.04:saturation=1.05",
}

LOUDNORM = "loudnorm=I=-14:TP=-1:LRA=11"


def grade_filter(grade: str) -> str | None:
    if grade.startswith("raw:"):
        return grade[4:]
    if grade in GRADES:
        return GRADES[grade]
    raise ValueError(f"Nieznany grade: {grade!r}")


def resolve_fps(prefs: dict, edl: dict, media: dict) -> float:
    fps = prefs["output"]["fps"]
    if fps != "source":
        return float(fps)
    # D-006: fps pierwszego źródła w order (wspólny fps warunkiem poprawnego concat -c copy)
    first_id = edl["order"][0]
    r = next(x for x in edl["ranges"] if x["id"] == first_id)
    stem = Path(edl["sources"][r["source"]]).stem
    return float(media["sources"][stem]["fps"])


@functools.lru_cache(maxsize=None)
def ffmpeg_has_filter(name: str) -> bool:
    """Czy ten build ffmpeg ma dany filtr (np. 'ass' wymaga libass)."""
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == name:
            return True
    return False


def _run_ffmpeg(args: list[str], log) -> None:
    proc = subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + args,
                          capture_output=True, text=True)
    if proc.stderr:
        log(proc.stderr.strip())
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg zakończył się błędem: {proc.stderr.strip()[-2000:]}")


def render_segment(
    src: Path, out: Path, r: dict, fmt: str, short_side: int, fps: float,
    fade_s: float, crf: int, preset: str, log,
) -> None:
    start, end = float(r["start"]), float(r["end"])
    dur = end - start
    crop_expr, dims = FORMAT_SPECS[fmt]
    w, h = dims(short_side)
    vf = []
    if crop_expr:
        vf.append(crop_expr.format(crop_x=float(r.get("crop_x", 0.5))))
    vf.append(f"scale={w}:{h}")
    vf.append(f"fps={fps}")
    af = []
    if r.get("mute"):
        af.append("volume=0")
    fade_out_start = max(0.0, dur - fade_s)
    af.append(f"afade=t=in:st=0:d={fade_s}")
    af.append(f"afade=t=out:st={fade_out_start:.4f}:d={fade_s}")
    af.append("aresample=48000")
    _run_ffmpeg(
        [
            "-ss", f"{start:.4f}", "-t", f"{dur:.4f}", "-i", str(src),
            "-vf", ",".join(vf), "-af", ",".join(af),
            "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-ac", "2",
            "-c:a", "aac", "-b:a", "192k",
            "-video_track_timescale", "90000",
            str(out),
        ],
        log,
    )


def _ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def render_format(
    project: Path, edl: dict, transcripts: dict, prefs: dict, fmt: str,
    vdir: Path, proxy_render: bool, fps: float, log, progress,
) -> Path:
    short_side = 540 if proxy_render else int(prefs["output"]["resolution"])
    crf = 28 if proxy_render else 18
    preset = "ultrafast" if proxy_render else "medium"
    fade_s = prefs["audio"]["fade_ms"] / 1000.0
    ranges = {r["id"]: r for r in edl["ranges"]}
    order = edl["order"]

    with tempfile.TemporaryDirectory(prefix=f"kadr-render-{fmt}-") as tmp:
        tmpdir = Path(tmp)
        seg_files = []
        for i, rid in enumerate(order):
            r = ranges[rid]
            src = Path(project) / edl["sources"][r["source"]]
            seg = tmpdir / f"seg{i:03d}.mp4"
            log(f"[{fmt}] segment {i + 1}/{len(order)}: {rid} ({r['start']}-{r['end']}s)")
            render_segment(src, seg, r, fmt, short_side, fps, fade_s, crf, preset, log)
            seg_files.append(seg)
            progress()

        concat_list = tmpdir / "concat.txt"
        concat_list.write_text("".join(f"file '{p}'\n" for p in seg_files))
        concatenated = tmpdir / "concat.mp4"
        _run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat_list),
                     "-c", "copy", str(concatenated)], log)

        # Finalny przebieg: grade → napisy (NA KOŃCU łańcucha) + loudnorm
        vf = []
        gf = grade_filter(prefs.get("grade", "none"))
        if gf:
            vf.append(gf)
        if subtitles.has_subtitles(edl):
            if not ffmpeg_has_filter("ass"):
                raise RuntimeError(
                    "Ten ffmpeg jest zbudowany bez libass (brak filtra 'ass') — nie mogę "
                    "wypalić napisów. Zainstaluj ffmpeg z libass, np. `brew reinstall ffmpeg`."
                )
            subtitles.validate_font(prefs["subtitles"]["font_family"])
            ass_path = vdir / f"master-{fmt}.ass"
            ass_path.write_text(subtitles.build_ass(edl, transcripts, prefs, fmt))
            # Escaping filtra ffmpeg: wewnątrz '...' escapujemy tylko \ i ' (NIE :).
            escaped = str(ass_path).replace("\\", "\\\\").replace("'", "\\'")
            vf.append(f"ass='{escaped}'")
        # loudnorm na całkowitej ciszy (wszystko zmutowane) daje NaN w ffmpeg — pomiń
        any_audio = any(not ranges[rid].get("mute") for rid in order)
        af = [LOUDNORM] if prefs["audio"]["loudnorm"] and any_audio else []

        out = vdir / f"out-{fmt}.mp4"
        log(f"[{fmt}] finalny przebieg (grade/napisy/loudnorm)")
        final_args = ["-i", str(concatenated)]
        if vf:
            final_args += ["-vf", ",".join(vf)]
        if af:
            final_args += ["-af", ",".join(af)]
        final_args += [
            "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(out),
        ]
        _run_ffmpeg(final_args, log)
        progress()
    return out


def render_project(
    project: Path,
    proxy_render: bool = False,
    formats: list[str] | None = None,
    note: str = "",
    progress_cb=None,
) -> dict:
    """Pełny render do nowej wersji. Deterministyczny dla tego samego edl + źródeł."""
    project = Path(project)
    prefs = config.load_preferences(project)
    errors = edl_mod.check_project(project)
    if errors:
        raise ValueError("edl.json niepoprawny: " + "; ".join(errors))
    edl = edl_mod.load_edl(project)
    if not edl["order"]:
        raise ValueError("Pusty order — nie ma czego renderować.")
    media = probe.load_media(project)
    transcripts = transcribe.load_transcripts(project)
    formats = formats or prefs["output"]["formats"]
    for fmt in formats:
        if fmt not in FORMAT_SPECS:
            raise ValueError(f"Nieznany format: {fmt!r}")

    vdir = versions.create_version(project)
    log_path = config.edit_dir(project) / "log" / f"render-{vdir.name}-{int(time.time())}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "a")

    total_steps = len(formats) * (len(edl["order"]) + 1)
    done_steps = 0

    def log(msg: str) -> None:
        log_file.write(msg + "\n")
        log_file.flush()

    def progress() -> None:
        nonlocal done_steps
        done_steps += 1
        if progress_cb:
            progress_cb(round(100 * done_steps / total_steps))

    try:
        versions.snapshot_edl(project, vdir)
        fps = resolve_fps(prefs, edl, media)
        outputs = {}
        durations = {}
        for fmt in formats:
            out = render_format(project, edl, transcripts, prefs, fmt, vdir,
                                proxy_render, fps, log, progress)
            outputs[fmt] = str(out)
            durations[fmt] = round(_ffprobe_duration(out), 2)
        manifest = versions.write_manifest(vdir, formats, durations, note, proxy_render)
        log(f"OK: {vdir.name} {durations}")
        return {"version": vdir.name, "outputs": outputs, "manifest": manifest,
                "log": str(log_path)}
    except Exception as e:
        log(f"BŁĄD: {e}")
        raise
    finally:
        log_file.close()
