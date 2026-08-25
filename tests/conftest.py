import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tests.fixtures.make_fixtures import make_fixtures  # noqa: E402


def pick_font() -> str:
    out = subprocess.run(["fc-list", "--format", "%{family}\n"],
                         capture_output=True, text=True).stdout
    families = [f.strip() for line in out.splitlines() for f in line.split(",") if f.strip()]
    for pref in ("Menlo", "DejaVu Sans", "Liberation Sans", "Arial"):
        if pref in families:
            return pref
    return families[0] if families else "Sans"


@pytest.fixture(scope="session")
def fixture_clips() -> list[Path]:
    return make_fixtures(REPO / "tests" / "fixtures")


@pytest.fixture()
def whisper_stub(tmp_path, monkeypatch) -> Path:
    """Podstawia stub whisper-cli + atrapę modelu; zwraca plik licznika wywołań."""
    stub = tmp_path / "whisper-cli"
    stub.write_text(f"#!{sys.executable}\n" + (REPO / "tests" / "whisper_stub.py").read_text())
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    count_file = tmp_path / "stub_calls.txt"
    count_file.write_text("")
    home = tmp_path / "kadr_home"
    (home / "models").mkdir(parents=True)
    (home / "models" / "ggml-large-v3-turbo.bin").write_bytes(b"stub")
    monkeypatch.setenv("KADR_WHISPER_BIN", str(stub))
    monkeypatch.setenv("WHISPER_STUB_COUNT", str(count_file))
    monkeypatch.setenv("KADR_HOME", str(home))
    return count_file


@pytest.fixture()
def project(tmp_path, fixture_clips, whisper_stub) -> Path:
    """Projekt: 2 klipy + edit/ + preferences z fontem dostępnym w systemie."""
    import kadr
    from pipeline import config

    proj = tmp_path / "proj"
    proj.mkdir()
    for clip in fixture_clips:
        shutil.copy2(clip, proj / clip.name)
    assert kadr.main(["init", str(proj)]) == 0
    prefs = config.load_preferences(proj)
    prefs["subtitles"]["font_family"] = pick_font()
    config.save_preferences(proj, prefs)
    return proj


@pytest.fixture()
def transcribed_project(project) -> Path:
    import kadr

    assert kadr.main(["transcribe", "--project", str(project)]) == 0
    return project
