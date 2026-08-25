import json
import subprocess

import pytest

import kadr
from pipeline import config, edl as edl_mod, render


def test_full_pipeline_renders_versions(transcribed_project):
    if not render.ffmpeg_has_filter("ass"):
        pytest.skip("ffmpeg zbudowany bez libass — nie można wypalić napisów")
    proj = transcribed_project
    assert kadr.main(["plan", "--auto", "--project", str(proj)]) == 0
    assert kadr.main(["plan", "--check", "--project", str(proj)]) == 0

    # napisy tylko w wybranych segmentach
    edl = edl_mod.load_edl(proj)
    edl["ranges"][0]["subtitles"] = True
    edl_mod.save_edl(proj, edl)

    result = render.render_project(proj, proxy_render=True)
    assert result["version"] == "v001"
    out = config.edit_dir(proj) / "versions" / "v001" / "out-9x16.mp4"
    assert out.exists()
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(out)],
        capture_output=True, text=True, check=True).stdout)
    video = next(s for s in probe["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (540, 960)  # proxy 9x16

    # plik .ass zawiera dialogi tylko z zakresu z subtitles: true
    ass = (config.edit_dir(proj) / "versions" / "v001" / "master-9x16.ass").read_text()
    assert ass.count("Dialogue:") >= 1

    manifest = json.loads((config.edit_dir(proj) / "versions" / "v001" / "manifest.json").read_text())
    assert manifest["formats"] == ["9x16"]
    assert manifest["durations_s"]["9x16"] > 0

    # drugi render tworzy v002
    result2 = render.render_project(proj, proxy_render=True)
    assert result2["version"] == "v002"


def test_crop_x_changes_frame(transcribed_project):
    proj = transcribed_project
    kadr.main(["plan", "--auto", "--project", str(proj)])
    edl = edl_mod.load_edl(proj)
    edl["order"] = edl["order"][:1]
    for crop_x in (0.0, 1.0):
        edl["ranges"][0]["crop_x"] = crop_x
        edl["ranges"][0]["subtitles"] = False
        edl_mod.save_edl(proj, edl)
        render.render_project(proj, proxy_render=True)
    v1 = config.edit_dir(proj) / "versions" / "v001" / "out-9x16.mp4"
    v2 = config.edit_dir(proj) / "versions" / "v002" / "out-9x16.mp4"

    def frame(path):
        return subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-ss", "0.5", "-i", str(path),
             "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True, check=True).stdout

    assert frame(v1) != frame(v2)  # zmiana crop_x widocznie przesuwa kadr


def test_render_16x9_and_mute(transcribed_project):
    proj = transcribed_project
    kadr.main(["plan", "--auto", "--project", str(proj)])
    edl = edl_mod.load_edl(proj)
    edl["order"] = edl["order"][:1]
    edl["ranges"][0]["mute"] = True
    edl_mod.save_edl(proj, edl)
    result = render.render_project(proj, proxy_render=True, formats=["16x9"])
    out = result["outputs"]["16x9"]
    # zmutowany segment: maksymalna głośność bliska ciszy
    det = subprocess.run(
        ["ffmpeg", "-i", out, "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True).stderr
    max_line = next(line for line in det.splitlines() if "max_volume" in line)
    assert "-91.0 dB" in max_line or float(max_line.split()[-2]) < -60


def test_subtitles_without_libass_raises_clear_error(transcribed_project, monkeypatch):
    """Render z napisami na ffmpeg bez filtra 'ass' → czytelny błąd, nie krypticzny ffmpeg."""
    proj = transcribed_project
    kadr.main(["plan", "--auto", "--project", str(proj)])
    edl = edl_mod.load_edl(proj)
    edl["order"] = edl["order"][:1]
    edl["ranges"][0]["subtitles"] = True
    edl_mod.save_edl(proj, edl)
    monkeypatch.setattr(render, "ffmpeg_has_filter", lambda name: False)
    with pytest.raises(RuntimeError, match="zbudowany bez libass"):
        render.render_project(proj, proxy_render=True)
