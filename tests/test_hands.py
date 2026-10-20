"""Every hand renders non-empty pixels."""
from __future__ import annotations

import skia

from whatif import load_config
from whatif.render import hands


def test_every_hand_renders_non_empty():
    cfg = load_config()
    for name in hands.available():
        surface = skia.Surface(256, 256)
        canvas = surface.getCanvas()
        canvas.clear(skia.ColorBLACK)
        hands.draw_hand(canvas, cfg, name, 128, 128, 1.0, 0.0, 0.0)
        arr = surface.makeImageSnapshot().toarray()
        assert (arr[:, :, :3].sum(axis=2) > 0).any(), f"{name} rendered empty"