"""Timing math tests: sentence-boundary expansion, espeak estimation, scene timings."""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from whatif.voice import _estimate_espeak_words, _expand_sentence_boundaries
from whatif.render.engine import _scene_timings


def test_expand_sentence_boundaries_proportional():
    text = "One two three."
    events = [{"word": "One two three.", "start": 0.0, "end": 1.5,
               "kind": "SentenceBoundary"}]
    words = _expand_sentence_boundaries(text, events)
    assert [w["word"] for w in words] == ["One", "two", "three."]
    # monotonically increasing
    starts = [w["start"] for w in words]
    assert starts == sorted(starts)
    # total duration preserved
    assert math.isclose(words[-1]["end"], 1.5, abs_tol=1e-6)


def test_expand_word_boundaries_pass_through():
    events = [
        {"word": "One", "start": 0.0, "end": 0.4, "kind": "WordBoundary"},
        {"word": "two", "start": 0.4, "end": 0.9, "kind": "WordBoundary"},
    ]
    out = _expand_sentence_boundaries("One two", events)
    assert [(w["word"], w["start"], w["end"]) for w in out] == [
        ("One", 0.0, 0.4), ("two", 0.4, 0.9)
    ]


def test_estimate_espeak_words_total_seconds_preserved():
    text = "What if bees vanished? Nobody notices."
    words = _estimate_espeak_words(text, total_seconds=3.0)
    assert words[-1]["end"] == pytest.approx(3.0, abs=1e-3)
    assert [w["word"] for w in words][:4] == ["What", "if", "bees", "vanished?"]


def test_scene_timings_monotonic_and_capped():
    script = {
        "opening_question": "What if bees vanished?",
        "scenes": [
            {"index": 0, "caption": "What if bees vanished?",
             "time_label": "opening", "cast_ids": ["c1"], "props": [],
             "poses": {}, "faces": {}, "emphasis": [], "shake": False, "claims": []},
            {"index": 1, "caption": "Within an hour, flowers lose their visitors.",
             "time_label": "+1 hour", "cast_ids": ["c1"], "props": [],
             "poses": {}, "faces": {}, "emphasis": [], "shake": False, "claims": []},
            {"index": 2, "caption": "By day one, crops begin to fail.",
             "time_label": "+1 day", "cast_ids": ["c1"], "props": [],
             "poses": {}, "faces": {}, "emphasis": [], "shake": False, "claims": []},
        ],
        "cast": [{"id": "c1", "name": "A", "hair_style": "bob", "hair_color_idx": 0,
                  "accessory": "none", "accessory_color_idx": 0, "bust": True}],
    }
    voice = {"words": [
        {"word": "What", "start": 0.0, "end": 0.3},
        {"word": "if", "start": 0.3, "end": 0.4},
        {"word": "bees", "start": 0.4, "end": 0.8},
        {"word": "vanished?", "start": 0.8, "end": 1.2},
        {"word": "Within", "start": 1.5, "end": 1.7},
        {"word": "an", "start": 1.7, "end": 1.8},
        {"word": "hour", "start": 1.8, "end": 2.0},
        {"word": "By", "start": 3.5, "end": 3.6},
        {"word": "day", "start": 3.6, "end": 3.8},
        {"word": "one", "start": 3.8, "end": 4.0},
    ]}
    timings = _scene_timings(script, voice, target_seconds=30.0)
    assert timings[0]["start"] == 0.0
    assert timings[0]["end"] == pytest.approx(1.5, abs=1e-6)
    assert timings[1]["start"] == pytest.approx(1.5, abs=1e-6)
    assert timings[1]["end"] == pytest.approx(3.5, abs=1e-6)
    assert timings[2]["start"] == pytest.approx(3.5, abs=1e-6)
    assert timings[2]["end"] == 30.0
    for i in range(1, len(timings)):
        assert timings[i]["start"] >= timings[i - 1]["start"]