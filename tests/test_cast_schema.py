"""Cast size 1..5, bust flag, body path with/without bust, both render non-empty."""
from __future__ import annotations

import skia

from whatif import load_config
from whatif.render import characters as char_mod


def _serialize_path(path: skia.Path) -> bytes:
    """skia.Path.serialize() -> skia.Data; convert to bytes for comparison."""
    data = path.serialize()
    if hasattr(data, "bytes"):
        return data.bytes()
    return bytes(data)


def test_body_path_with_bust_differs_from_no_bust():
    cfg = load_config()
    with_bust = _serialize_path(char_mod.body_path(cfg, {"bust": True}))
    no_bust = _serialize_path(char_mod.body_path(cfg, {"bust": False}))
    assert with_bust != no_bust


def test_bust_size_zero_equals_no_bust():
    cfg = load_config()
    cfg["characters"]["bust_size"] = 0.0
    a = _serialize_path(char_mod.body_path(cfg, {"bust": True}))
    b = _serialize_path(char_mod.body_path(cfg, {"bust": False}))
    assert a == b


def test_character_renders_both_bust_and_plain():
    cfg = load_config()
    for bust in (True, False):
        surface = skia.Surface(512, 800)
        canvas = surface.getCanvas()
        canvas.clear(skia.ColorBLACK)
        canvas.translate(256, 60)
        char_mod.draw_character(canvas, cfg,
                                {"id": "c1", "bust": bust, "hair_style": "bob",
                                 "hair_color_idx": 0, "accessory": "none",
                                 "accessory_color_idx": 0},
                                0, 0, 1.0, t=1.0, pose="present", face="smile")
        arr = surface.makeImageSnapshot().toarray()
        assert (arr[:, :, :3].sum(axis=2) > 0).any()