import json
import time

import kadr
import pytest
from fastapi.testclient import TestClient
from pipeline import config, edl as edl_mod
from server.app import create_app


@pytest.fixture()
def client(transcribed_project):
    kadr.main(["plan", "--auto", "--project", str(transcribed_project)])
    app = create_app(transcribed_project)
    with TestClient(app) as c:
        c.project = transcribed_project
        yield c


def test_state_returns_full_project(client):
    state = client.get("/api/state").json()
    assert state["preferences"]["output"]["formats"] == ["9x16"]
    assert len(state["media"]["sources"]) == 2
    assert state["edl"]["version"] == 2
    assert "clip_a" in state["transcripts_index"]
    assert state["versions"] == []


def test_frame_returns_jpeg_and_crop_changes_it(client):
    r1 = client.get("/api/frame", params={"source": "clip_a", "t": 1.0, "height": 120})
    assert r1.status_code == 200
    assert r1.headers["content-type"] == "image/jpeg"
    r2 = client.get("/api/frame", params={"source": "clip_a", "t": 1.0, "height": 120,
                                          "format": "9x16", "crop_x": 0.0})
    r3 = client.get("/api/frame", params={"source": "clip_a", "t": 1.0, "height": 120,
                                          "format": "9x16", "crop_x": 1.0})
    assert r2.content != r3.content

    assert client.get("/api/frame", params={"source": "nope", "t": 0}).status_code == 404


def test_media_serves_proxy(client):
    res = client.get("/media/proxy/clip_a.mp4")
    assert res.status_code == 200
    assert res.headers["content-type"] == "video/mp4"


def test_ui_served_at_root(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "KADR" in res.text


def test_put_edl_saves_and_updates_timestamp(client):
    edl = client.get("/api/state").json()["edl"]
    edl["ranges"][0]["subtitles"] = True
    saved = client.put("/api/edl", json=edl)
    assert saved.status_code == 200
    on_disk = edl_mod.load_edl(client.project)
    assert on_disk["ranges"][0]["subtitles"] is True
    assert on_disk["meta"]["created_by"] == "ui"


def test_put_edl_conflict_409_then_force(client):
    edl = client.get("/api/state").json()["edl"]
    # zmiana "poza UI" (agent): inny updated_at na dysku
    agent_copy = json.loads(json.dumps(edl))
    agent_copy["meta"]["updated_at"] = "2020-01-01T00:00:00+00:00"
    edl_path = edl_mod.edl_path(client.project)
    edl_path.write_text(json.dumps(agent_copy))

    res = client.put("/api/edl", json=edl)
    assert res.status_code == 409
    assert "disk_updated_at" in res.json()

    res = client.put("/api/edl?force=true", json=edl)
    assert res.status_code == 200


def test_put_edl_validation_422(client):
    edl = client.get("/api/state").json()["edl"]
    edl["ranges"][0]["start"] = 99.0
    assert client.put("/api/edl", json=edl).status_code == 422


def test_put_preferences_validates(client):
    prefs = client.get("/api/state").json()["preferences"]
    prefs["output"]["formats"] = ["4x3"]
    assert client.put("/api/preferences", json=prefs).status_code == 422
    prefs["output"]["formats"] = ["16x9"]
    res = client.put("/api/preferences", json=prefs)
    assert res.status_code == 200
    assert config.load_preferences(client.project)["output"]["formats"] == ["16x9"]


def test_fonts_listed(client):
    fonts = client.get("/api/fonts").json()["fonts"]
    assert isinstance(fonts, list) and fonts


def test_render_requires_approved(client):
    res = client.post("/api/render", json={"proxy": True})
    assert res.status_code == 400
    assert "approved" in res.json()["detail"]


def test_render_via_api_creates_version(client):
    edl = client.get("/api/state").json()["edl"]
    edl["approved"] = True
    edl["order"] = edl["order"][:1]
    assert client.put("/api/edl", json=edl).status_code == 200

    assert client.post("/api/render", json={"proxy": True, "note": "z UI"}).json()["started"]
    for _ in range(120):
        st = client.get("/api/render/status").json()
        if not st["running"] and (st["last_version"] or st["error"]):
            break
        time.sleep(0.5)
    assert st["error"] is None
    assert st["last_version"] == "v001"
    assert st["progress_pct"] == 100

    versions = client.get("/api/state").json()["versions"]
    assert versions[0]["version"] == "v001"
    assert versions[0]["manifest"]["note"] == "z UI"
    out = client.get(versions[0]["outputs"]["9x16"])
    assert out.status_code == 200 and out.headers["content-type"] == "video/mp4"
