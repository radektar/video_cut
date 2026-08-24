from pipeline.subtitles import ass_time, build_ass, build_events, hex_to_ass

TRANSCRIPT = {
    "clip_a": {
        "source": "clip_a.mp4",
        "words": [
            {"text": "Ala", "start": 1.0, "end": 1.3},
            {"text": "ma", "start": 1.4, "end": 1.6},
            {"text": "kota", "start": 1.7, "end": 2.0},
            {"text": "psa", "start": 4.0, "end": 4.4},
        ],
    }
}


def make_edl(sub1=True, sub2=True) -> dict:
    return {
        "version": 2,
        "sources": {"clip_a": "clip_a.mp4"},
        "ranges": [
            {"id": "r1", "source": "clip_a", "start": 0.5, "end": 2.5, "subtitles": sub1},
            {"id": "r2", "source": "clip_a", "start": 3.5, "end": 5.0, "subtitles": sub2},
        ],
        "order": ["r1", "r2"],
    }


def test_offsets_shift_by_preceding_segments():
    events = build_events(make_edl(), TRANSCRIPT, chunk_size=3, upper=False)
    # r1: słowa 1.0-2.0 przy starcie 0.5 → event 0.5-1.5 w osi wyjścia
    assert events[0]["text"] == "Ala ma kota"
    assert abs(events[0]["start"] - 0.5) < 1e-6
    assert abs(events[0]["end"] - 1.5) < 1e-6
    # r2 zaczyna się w osi wyjścia po 2.0 s (czas r1); słowo 4.0-4.4 → 2.5-2.9
    assert events[1]["text"] == "psa"
    assert abs(events[1]["start"] - 2.5) < 1e-6
    assert abs(events[1]["end"] - 2.9) < 1e-6


def test_only_ranges_with_subtitles_true():
    events = build_events(make_edl(sub1=False), TRANSCRIPT, chunk_size=3, upper=False)
    assert [e["text"] for e in events] == ["psa"]
    # offset drugiego segmentu nadal uwzględnia czas pierwszego
    assert abs(events[0]["start"] - 2.5) < 1e-6


def test_chunking_and_upper():
    events = build_events(make_edl(sub2=False), TRANSCRIPT, chunk_size=2, upper=True)
    assert [e["text"] for e in events] == ["ALA MA", "KOTA"]


def test_event_clamped_to_segment_duration():
    edl = make_edl()
    edl["ranges"][0]["end"] = 1.9  # słowo "kota" (do 2.0) wystaje poza koniec
    events = build_events(edl, TRANSCRIPT, chunk_size=3, upper=False)
    assert events[0]["end"] <= 1.9 - 0.5 + 1e-6


def test_ass_time_format():
    assert ass_time(0.0) == "0:00:00.00"
    assert ass_time(61.25) == "0:01:01.25"


def test_hex_to_ass_bgr_order():
    assert hex_to_ass("#FF8000") == "&H000080FF"


def test_build_ass_contains_style_and_dialogues():
    prefs = {
        "subtitles": {
            "font_family": "TestFont", "font_size": 20, "case": "natural",
            "chunk_words": 3, "margin_v": 70, "primary_color": "#FFFFFF",
            "outline_color": "#000000", "outline": 2,
        }
    }
    ass = build_ass(make_edl(), TRANSCRIPT, prefs, "9x16")
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    assert "TestFont" in ass
    assert ass.count("Dialogue:") == 2
