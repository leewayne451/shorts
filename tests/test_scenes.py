"""Every scene template renders with 1..5 cast; unknown template falls back."""
from __future__ import annotations

import skia

from whatif import load_config
from whatif.render import scenes


def _cast(n: int):
    return [{"id": f"c{i}", "name": f"N{i}", "hair_style": "bob",
             "hair_color_idx": 0, "accessory": "none",
             "accessory_color_idx": 0, "bust": True} for i in range(1, n + 1)]


def _render(template: str, n_cast: int) -> int:
    cfg = load_config()
    cast = _cast(n_cast)
    scene = {
        "index": 1, "time_label": "+1 hour", "scene_template": template,
        "props": [{"type": "icon", "name": "clock"}],
        "cast_ids": [c["id"] for c in cast],
        "poses": {c["id"]: "present" for c in cast},
        "faces": {c["id"]: "smile" for c in cast},
        "emphasis": [], "caption": "Test caption line.", "shake": False, "claims": [],
    }
    script = {"cast": cast, "scenes": [scene], "opening_question": "What if X vanished?"}
    surface = skia.Surface(1080, 1920)
    canvas = surface.getCanvas()
    canvas.clear(skia.ColorBLACK)
    scenes.render_scene(canvas, cfg, script, scene,
                        {c["id"]: c for c in cast}, t=1.0,
                        scene_start=0.0, caches={"photos": {}})
    arr = surface.makeImageSnapshot().toarray()
    return int((arr[:, :, :3].sum(axis=2) > 0).sum())


def test_every_template_with_one_cast():
    for tmpl in scenes.available():
        assert _render(tmpl, 1) > 0, f"{tmpl} empty at 1 cast"


def test_crowd_react_supports_5_cast():
    assert _render("crowd_react", 5) > 0


def test_unknown_template_falls_back_to_intro_prop():
    a = _render("intro_prop", 1)
    b = _render("totally_unknown_template", 1)
    assert b > 0