"""Per-beat caption layout and drawing."""
from __future__ import annotations

import skia

from whatif import load_config
from whatif.render.captions import layout_line, draw_caption_line, caption_appears


def _cfg():
    return load_config()


def test_layout_returns_placements_for_simple_text():
    cfg = _cfg()
    placements = layout_line("Within one hour cars stop moving",
                             ["cars", "moving"], cfg)
    assert len(placements) == len("Within one hour cars stop moving".split())


def test_emphasis_colored_yellow():
    cfg = _cfg()
    placements = layout_line("bees vanish", ["bees"], cfg)
    bees = [p for p in placements if p.word.lower() == "bees"][0]
    assert tuple(bees.color) == tuple(cfg["colors"]["caption_active"])


def test_non_emphasis_white():
    cfg = _cfg()
    placements = layout_line("bees vanish", ["bees"], cfg)
    vanish = [p for p in placements if p.word.lower() == "vanish"][0]
    assert tuple(vanish.color) == tuple(cfg["colors"]["caption_white"])


def test_caption_appears_substring():
    cfg = _cfg()
    placements = layout_line("By day one crops fail", [], cfg)
    assert caption_appears(placements, "day one")
    assert not caption_appears(placements, "zebra")


def test_draw_caption_line_renders_non_empty_pixels():
    cfg = _cfg()
    surface = skia.Surface(1080, 1920)
    canvas = surface.getCanvas()
    canvas.clear(skia.ColorBLACK)
    placements = layout_line("What if bees vanished?", ["bees"], cfg)
    draw_caption_line(canvas, cfg, placements, 540, 1500, popin_t0=0.0, t=1.0)
    snap = surface.makeImageSnapshot()
    arr = snap.toarray()
    assert (arr[:, :, :3].sum(axis=2) > 0).any()