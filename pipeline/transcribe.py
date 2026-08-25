"""whisper.cpp → edit/transcripts/<stem>.json (format sekcja 6.3, cache po sha256)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pipeline import config

WHISPER_CANDIDATES = ("whisper-cli", "whisper-cpp", "whisper")


def find_whisper_binary(prefs: dict) -> str:
    env = os.environ.get("KADR_WHISPER_BIN")
    if env:
        return env
    configured = prefs.get("whisper", {}).get("binary", "auto")
    if configured and configured != "auto":
        return configured
    for name in WHISPER_CANDIDATES:
        found = shutil.which(name)
        if found:
            return found
    raise RuntimeError(
        "Nie znaleziono binarki whisper.cpp (whisper-cli). Zainstaluj: brew install whisper-cpp, "
        "albo wskaż ścieżkę w preferences.yaml (whisper.binary) lub KADR_WHISPER_BIN."
    )


def model_path(prefs: dict) -> Path:
    model = prefs.get("whisper", {}).get("model", "large-v3-turbo")
    path = config.kadr_home() / "models" / f"ggml-{model}.bin"
    if not path.exists():
        raise RuntimeError(
            f"Brak modelu whispera: {path}. Pobierz: curl -L -o {path} "
            f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{model}.bin"
        )
    return path


def extract_wav(src: Path, wav: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)],
        check=True,
    )


def tokens_to_words(transcription: list[dict]) -> list[dict]:
    """Tokeny BPE → słowa: sklejaj tokeny do spacji; pomiń tokeny specjalne [_..._]."""
    words: list[dict] = []
    for seg in transcription:
        for tok in seg.get("tokens", []):
            text = tok.get("text", "")
            if text.startswith("[_") or not text.strip():
                continue
            start = tok["offsets"]["from"] / 1000.0
            end = tok["offsets"]["to"] / 1000.0
            if text.startswith(" ") or not words:
                words.append({"text": text.strip(), "start": start, "end": end})
            else:
                words[-1]["text"] += text
                words[-1]["end"] = end
    return [w for w in words if w["text"]]


def parse_whisper_json(raw: dict, source_name: str, sha256: str, engine: str) -> dict:
    transcription = raw.get("transcription", [])
    segments = [
        {
            "start": seg["offsets"]["from"] / 1000.0,
            "end": seg["offsets"]["to"] / 1000.0,
            "text": seg.get("text", "").strip(),
        }
        for seg in transcription
        if seg.get("text", "").strip()
    ]
    return {
        "source": source_name,
        "sha256": sha256,
        "language": raw.get("result", {}).get("language", "pl"),
        "engine": engine,
        "words": tokens_to_words(transcription),
        "segments": segments,
    }


def transcript_path(project: Path, stem: str) -> Path:
    return config.edit_dir(project) / "transcripts" / f"{stem}.json"


def transcribe_source(project: Path, stem: str, entry: dict, prefs: dict) -> None:
    binary = find_whisper_binary(prefs)
    model = model_path(prefs)
    lang = prefs.get("language", "pl")
    src = Path(project) / entry["file"]
    with tempfile.TemporaryDirectory(prefix="kadr-whisper-") as tmp:
        wav = Path(tmp) / "audio.wav"
        extract_wav(src, wav)
        out_prefix = Path(tmp) / "out"
        subprocess.run(
            [binary, "-m", str(model), "-l", lang, "-f", str(wav),
             "--output-json-full", "-of", str(out_prefix), "-ml", "1"],
            check=True, capture_output=True,
        )
        raw = json.loads((out_prefix.with_suffix(".json")).read_text())
    engine = f"whisper.cpp/{prefs.get('whisper', {}).get('model', 'large-v3-turbo')}"
    transcript = parse_whisper_json(raw, entry["file"], entry["sha256"], engine)
    path = transcript_path(project, stem)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(transcript, indent=2, ensure_ascii=False))
    tmp_path.rename(path)


def transcribe_project(project: Path, media: dict, max_workers: int = 2) -> dict:
    """Transkrybuje źródła bez aktualnego transkryptu (cache po sha256). Pula 2 procesów."""
    prefs = config.load_preferences(project)
    todo = []
    cached = 0
    for stem, entry in media["sources"].items():
        path = transcript_path(project, stem)
        if path.exists():
            try:
                existing = json.loads(path.read_text())
            except json.JSONDecodeError:
                existing = {}
            if existing.get("sha256") == entry["sha256"]:
                cached += 1
                continue
        todo.append((stem, entry))
    if todo:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(transcribe_source, project, s, e, prefs) for s, e in todo]
            for f in futures:
                f.result()
    return {"transcribed": len(todo), "cached": cached}


def load_transcripts(project: Path) -> dict:
    """stem → transkrypt (tylko istniejące pliki)."""
    out = {}
    tdir = config.edit_dir(project) / "transcripts"
    if tdir.is_dir():
        for path in sorted(tdir.glob("*.json")):
            out[path.stem] = json.loads(path.read_text())
    return out
