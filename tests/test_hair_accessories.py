"""Every hair style / accessory renders; unknown values fall back to defaults."""
from __future__ import annotations

import skia

from whatif import load_config
from whatif.render import hair_accessories as ha


def _draw_with(style=None, acc=None) -> int:
    cfg = load_config()
    spec = {"id": "c1", "hair_style": style, "hair_color_idx": 0,
            "accessory": acc, "accessory_color_idx": 0, "bust": True}
    surface = skia.Surface(512, 512)
    canvas = surface.getCanvas()
    canvas.clear(skia.ColorBLACK)
    canvas.translate(256, 200)
    ha.draw_hair_back(canvas, cfg, spec, sick=False)
    ha.draw_accessory(canvas, cfg, spec)
    arr = surface.makeImageSnapshot().toarray()
    return int((arr[:, :, :3].sum(axis=2) > 0).sum())


def test_every_hair_style_renders():
    for style in ha.available_hair_styles():
        assert _draw_with(style=style) > 0, f"hair {style} empty"


def test_every_accessory_renders():
    for acc in ha.available_accessories():
        assert _draw_with(acc=acc) > 0, f"accessory {acc} empty"


def test_unknown_hair_falls_back_to_bob():
    bob_pixels = _draw_with(style="bob")
    unknown_pixels = _draw_with(style="definitely_not_a_hair_style")
    assert unknown_pixels == bob_pixels


def test_unknown_accessory_falls_back_to_none():
    none_pixels = _draw_with(acc="none")
    unknown_pixels = _draw_with(acc="definitely_not_an_accessory")
    assert unknown_pixels == none_pixels