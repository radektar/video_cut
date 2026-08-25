import json

import kadr
from pipeline import config, transcribe


def stub_calls(count_file) -> int:
    return len(count_file.read_text().splitlines())


def test_second_run_uses_cache(project, whisper_stub):
    assert kadr.main(["transcribe", "--project", str(project)]) == 0
    first = stub_calls(whisper_stub)
    assert first == 2  # 2 klipy

    assert kadr.main(["transcribe", "--project", str(project)]) == 0
    assert stub_calls(whisper_stub) == first  # drugi bieg = 0 wywołań whispera


def test_changed_hash_triggers_retranscription(project, whisper_stub):
    assert kadr.main(["transcribe", "--project", str(project)]) == 0
    first = stub_calls(whisper_stub)
    tpath = transcribe.transcript_path(project, "clip_a")
    data = json.loads(tpath.read_text())
    data["sha256"] = "0" * 64
    tpath.write_text(json.dumps(data))

    assert kadr.main(["transcribe", "--project", str(project)]) == 0
    assert stub_calls(whisper_stub) == first + 1  # tylko clip_a ponownie


def test_transcript_format(transcribed_project):
    tpath = transcribe.transcript_path(transcribed_project, "clip_a")
    data = json.loads(tpath.read_text())
    assert data["source"] == "clip_a.mp4"
    assert len(data["sha256"]) == 64
    assert data["language"] == "pl"
    assert data["engine"].startswith("whisper.cpp/")
    # tokeny BPE " pier" + "wsze" sklejone w jedno słowo
    words = [w["text"] for w in data["words"]]
    assert "pierwsze" in words
    assert all(w["start"] <= w["end"] for w in data["words"])
    assert data["segments"] and data["segments"][0]["text"]


def test_transcribe_builds_proxy_with_cache(project):
    assert kadr.main(["transcribe", "--project", str(project)]) == 0
    pdir = config.edit_dir(project) / "proxy"
    assert (pdir / "clip_a.mp4").exists() and (pdir / "clip_b.mp4").exists()
    mtime = (pdir / "clip_a.mp4").stat().st_mtime_ns
    assert kadr.main(["proxy", "--project", str(project)]) == 0
    assert (pdir / "clip_a.mp4").stat().st_mtime_ns == mtime  # cache, bez przebudowy
