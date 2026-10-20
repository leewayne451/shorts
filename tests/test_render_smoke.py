"""3-frame render smoke test using fallback icons (no network, no ffmpeg).

We call scenes.render_scene + captions directly, not the full ffmpeg pipeline.
"""
from __future__ import annotations

import skia

from whatif import load_config
from whatif.render import scenes, captions


def test_three_frame_smoke():
    cfg = load_config()
    cast = [{"id": "c1", "name": "A", "hair_style": "bob", "hair_color_idx": 0,
             "accessory": "none", "accessory_color_idx": 0, "bust": True}]
    scene = {
        "index": 1, "time_label": "+1 hour", "scene_template": "timeline_step",
        "props": [{"type": "icon", "name": "question_mark"}],
        "cast_ids": ["c1"], "poses": {"c1": "present"}, "faces": {"c1": "smile"},
        "emphasis": ["nothing"], "caption": "Within an hour, nothing pollinates.",
        "shake": True, "claims": [],
    }
    script = {"cast": cast, "scenes": [scene], "opening_question": "What if X vanished?"}
    placements = captions.layout_line(scene["caption"], scene["emphasis"], cfg)
    surface = skia.Surface(1080, 1920)
    for t in (0.0, 0.5, 1.0):
        canvas = surface.getCanvas()
        canvas.clear(skia.ColorBLACK)
        scenes.render_scene(canvas, cfg, script, scene,
                            {"c1": cast[0]}, t=t, scene_start=0.0,
                            caches={"photos": {}})
        captions.draw_caption_line(canvas, cfg, placements, 540, 1500, 0.0, t)
        arr = surface.makeImageSnapshot().toarray()
        assert (arr[:, :, :3].sum(axis=2) > 0).any()