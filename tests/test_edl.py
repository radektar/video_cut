from pipeline.edl import validate_edl


def base_edl() -> dict:
    return {
        "version": 2,
        "project": "test",
        "sources": {"clip_a": "clip_a.mp4"},
        "ranges": [
            {"id": "r1", "source": "clip_a", "start": 0.5, "end": 2.0,
             "subtitles": True, "crop_x": 0.5, "mute": False, "locked": False},
        ],
        "order": ["r1"],
        "approved": False,
        "meta": {"created_by": "agent", "updated_at": "2026-01-01T00:00:00+00:00"},
    }


MEDIA = {"sources": {"clip_a": {"file": "clip_a.mp4", "duration": 6.0}}}


def test_valid_edl_passes():
    assert validate_edl(base_edl(), MEDIA) == []


def test_start_must_be_before_end():
    edl = base_edl()
    edl["ranges"][0]["start"] = 2.0
    edl["ranges"][0]["end"] = 2.0
    assert any("start < end" in e for e in validate_edl(edl, MEDIA))


def test_negative_start_rejected():
    edl = base_edl()
    edl["ranges"][0]["start"] = -0.1
    assert any("start < 0" in e for e in validate_edl(edl, MEDIA))


def test_end_beyond_source_duration():
    edl = base_edl()
    edl["ranges"][0]["end"] = 7.5
    assert any("poza trwaniem" in e for e in validate_edl(edl, MEDIA))


def test_crop_x_out_of_range():
    edl = base_edl()
    edl["ranges"][0]["crop_x"] = 1.5
    assert any("crop_x" in e for e in validate_edl(edl, MEDIA))


def test_unknown_source_in_range():
    edl = base_edl()
    edl["ranges"][0]["source"] = "nope"
    assert any("nie występuje w sources" in e for e in validate_edl(edl, MEDIA))


def test_order_with_unknown_id():
    edl = base_edl()
    edl["order"] = ["r1", "r9"]
    assert any("nieznane id" in e for e in validate_edl(edl, MEDIA))


def test_order_with_duplicate_id():
    edl = base_edl()
    edl["order"] = ["r1", "r1"]
    assert any("zduplikowane" in e for e in validate_edl(edl, MEDIA))


def test_duplicate_range_ids():
    edl = base_edl()
    edl["ranges"].append(dict(edl["ranges"][0]))
    assert any("zduplikowane id" in e for e in validate_edl(edl, MEDIA))


def test_absolute_source_path_rejected():
    edl = base_edl()
    edl["sources"]["clip_a"] = "/abs/clip_a.mp4"
    assert any("względna" in e for e in validate_edl(edl))


def test_order_may_omit_ranges_trash():
    # usunięcie segmentu = usunięcie z order; obiekt zostaje w ranges (kosz)
    edl = base_edl()
    edl["ranges"].append({"id": "r2", "source": "clip_a", "start": 3.0, "end": 4.0})
    assert validate_edl(edl, MEDIA) == []
