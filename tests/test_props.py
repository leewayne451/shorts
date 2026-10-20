"""All 5 icons render non-empty pixels; unknown icon falls back to question_mark."""
from __future__ import annotations

import skia

from whatif import load_config
from whatif.render import props


def _render(name: str) -> int:
    cfg = load_config()
    surface = skia.Surface(256, 256)
    canvas = surface.getCanvas()
    canvas.clear(skia.ColorBLACK)
    props.draw_icon(canvas, cfg, name, 128, 128, 1.0, 0.0)
    arr = surface.makeImageSnapshot().toarray()
    return int((arr[:, :, :3].sum(axis=2) > 0).sum())


def test_every_icon_renders_non_empty():
    for name in props.available():
        assert _render(name) > 0, f"{name} rendered empty"


def test_unknown_icon_falls_back_to_question_mark():
    q_pixels = _render("question_mark")
    unknown_pixels = _render("definitely_not_an_icon")
    assert unknown_pixels == q_pixels