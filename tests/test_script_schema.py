"""Script schema hard rules."""
from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from whatif.script_stage import Script


def _base():
    cast = [{"id": "c1", "name": "A", "hair_style": "bob", "hair_color_idx": 0,
             "accessory": "none", "accessory_color_idx": 0, "bust": True}]
    opening = {
        "index": 0, "time_label": "opening", "scene_template": "intro_prop",
        "props": [{"type": "photo", "query": "honey jar"}],
        "cast_ids": ["c1"], "poses": {"c1": "present"}, "faces": {"c1": "smile"},
        "emphasis": ["bees"], "caption": "What if bees vanished?",
        "shake": False, "claims": [],
    }
    cons1 = {
        "index": 1, "time_label": "+1 hour", "scene_template": "timeline_step",
        "props": [{"type": "icon", "name": "clock"}],
        "cast_ids": ["c1"], "poses": {"c1": "present"}, "faces": {"c1": "open"},
        "emphasis": [], "caption": "Within an hour, nothing pollinates.",
        "shake": False, "claims": [],
    }
    cons2 = {
        "index": 2, "time_label": "+1 day", "scene_template": "crowd_react",
        "props": [{"type": "icon", "name": "no_sign"}],
        "cast_ids": ["c1"], "poses": {"c1": "shrug"}, "faces": {"c1": "meh"},
        "emphasis": [], "caption": "By day one, grocery shelves start to empty.",
        "shake": False, "claims": [],
    }
    cons3 = {
        "index": 3, "time_label": "+1 week", "scene_template": "big_number",
        "props": [], "cast_ids": ["c1"], "poses": {"c1": "point"},
        "faces": {"c1": "smile"},
        "emphasis": [], "caption": "By week one, prices for almonds double.",
        "shake": False, "claims": [],
    }
    return {"title": "Bees", "opening_question": "What if bees vanished?",
            "cast": cast, "scenes": [opening, cons1, cons2, cons3]}


def test_base_script_passes():
    Script(**_base())


def test_opening_must_match_pattern():
    bad = _base()
    bad["opening_question"] = "Bees are gone"
    bad["scenes"][0]["caption"] = "Bees are gone"
    with pytest.raises(ValidationError):
        Script(**bad)


def test_cast_size_bounds():
    s = _base()
    s["cast"] = []
    with pytest.raises(ValidationError):
        Script(**s)


def test_missing_required_time_labels_fails():
    s = _base()
    del s["scenes"][2]  # removes "+1 day"
    for i, sc in enumerate(s["scenes"]):
        sc["index"] = i
    with pytest.raises(ValidationError):
        Script(**s)


def test_unknown_prop_type_fails():
    s = _base()
    s["scenes"][1]["props"] = [{"type": "video", "url": "x"}]
    with pytest.raises(ValidationError):
        Script(**s)


def test_too_few_scenes_fails():
    s = _base()
    s["scenes"] = s["scenes"][:3]
    with pytest.raises(ValidationError):
        Script(**s)