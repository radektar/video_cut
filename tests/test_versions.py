import json

from pipeline import versions


def test_numbering_starts_at_v001(tmp_path):
    proj = tmp_path / "p"
    (proj / "edit").mkdir(parents=True)
    assert versions.next_version(proj) == "v001"
    vdir = versions.create_version(proj)
    assert vdir.name == "v001"
    assert versions.next_version(proj) == "v002"


def test_numbering_continues_after_gap(tmp_path):
    proj = tmp_path / "p"
    (proj / "edit" / "versions" / "v001").mkdir(parents=True)
    (proj / "edit" / "versions" / "v007").mkdir()
    (proj / "edit" / "versions" / "notaversion").mkdir()
    assert versions.next_version(proj) == "v008"
    assert versions.list_versions(proj) == ["v001", "v007"]


def test_manifest_contents(tmp_path):
    proj = tmp_path / "p"
    (proj / "edit").mkdir(parents=True)
    vdir = versions.create_version(proj)
    (vdir / "edl.json").write_text('{"version": 2}')
    manifest = versions.write_manifest(vdir, ["9x16"], {"9x16": 20.64}, note="test", proxy=True)
    on_disk = json.loads((vdir / "manifest.json").read_text())
    assert on_disk == manifest
    assert on_disk["version"] == "v001"
    assert on_disk["formats"] == ["9x16"]
    assert on_disk["durations_s"] == {"9x16": 20.64}
    assert len(on_disk["edl_sha256"]) == 64
    assert on_disk["note"] == "test"
