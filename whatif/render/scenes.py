"""Scene templates (6) and per-scene layout for 1..5 cast members.

Each renderer takes:
  canvas, cfg, script, scene, cast, t, scene_start, scene_end, caches
and draws the scene for time t in [scene_start, scene_end].

Slot layouts return center positions for characters and props in canvas space.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import skia

from whatif import get_logger
from whatif.render import characters as char_mod
from whatif.render import hands as hands_mod
from whatif.render import props as props_mod
from whatif.render.captions import layout_line, draw_caption_line
from whatif.render.photos import draw_card, load_image_skia

_LOG = get_logger("whatif.render.scenes")

_TEMPLATES = {"intro_prop", "timeline_step", "crowd_react",
              "two_reactors", "two_props_compare", "big_number"}

# Pose -> (left_hand, right_hand) with rotation and offsets (dx,dy).
_POSE_HANDS = {
    "idle":      (None, None),
    "present":   ("open_palm", "open_palm"),
    "point":     ("point_right", "point_left"),
    "pinch":     ("pinch", "pinch"),
    "shrug":     ("palm_up", "palm_up"),
    "think":     ("point_up", None),
    "wave":      ("wave", None),
    "celebrate": ("open_palm", "open_palm"),
}


def _slots(visible_ids: List[str], cfg: Dict[str, Any]) -> List[Tuple[float, float]]:
    """Return (x,y) center positions for head-top-center of each visible character."""
    w = float(cfg["video"]["width"])
    h = float(cfg["video"]["height"])
    safe_top = float(cfg["video"]["safe_top_px"])
    safe_bot = float(cfg["video"]["safe_bottom_px"])
    usable_y = h - safe_top - safe_bot
    cy = safe_top + usable_y * 0.55
    n = len(visible_ids)
    if n == 1:
        return [(w / 2.0, cy)]
    if n == 2:
        return [(w * 0.35, cy), (w * 0.65, cy)]
    if n == 3:
        return [(w * 0.22, cy), (w * 0.50, cy), (w * 0.78, cy)]
    if n == 4:
        return [(w * 0.22, cy - 20), (w * 0.78, cy - 20),
                (w * 0.35, cy + 260), (w * 0.65, cy + 260)]
    return [(w * 0.15, cy), (w * 0.32, cy), (w * 0.50, cy),
            (w * 0.68, cy), (w * 0.85, cy)]


def _draw_cast(canvas, cfg, script, scene, t, cast_by_id, scene_start):
    visible = scene.get("cast_ids") or [c["id"] for c in script["cast"]]
    visible = [cid for cid in visible if cid in cast_by_id]
    slots = _slots(visible, cfg)
    for cid, (sx, sy) in zip(visible, slots):
        spec = cast_by_id[cid]
        pose = scene.get("poses", {}).get(cid, "idle")
        face = scene.get("faces", {}).get(cid, "smile")
        sick = face == "ew" and pose == "pinch"
        char_mod.draw_character(canvas, cfg, spec, sx, sy, 1.0, t,
                                pose=pose, face=face, sick=sick)
        # Hands
        lh, rh = _POSE_HANDS.get(pose, (None, None))
        anchors = char_mod.hands_anchor(cfg, spec)
        for hand_name, (hx, hy) in ((lh, anchors["left"]), (rh, anchors["right"])):
            if hand_name is None:
                continue
            # Local -> canvas
            canvas.save()
            canvas.translate(sx, sy)
            canvas.translate(hx, hy)
            hands_mod.draw_hand(canvas, cfg, hand_name, 0.0, 0.0, 0.95, 0.0, t)
            canvas.restore()


def _draw_prop(canvas, cfg, prop, cx, cy, size, t, popin_t0, caches):
    if prop.get("type") == "photo":
        img = caches["photos"].get(prop["query"])
        draw_card(canvas, cfg, img, cx, cy, size,
                  float(cfg["photos"]["card_outline_px"]), t, popin_t0)
    elif prop.get("type") == "icon":
        props_mod.draw_icon(canvas, cfg, prop["name"], cx, cy, size / 200.0, t)
    # An intro_prop may overlay no_sign on a photo when the subject vanishes.
    if prop.get("overlay_no_sign"):
        props_mod.draw_icon(canvas, cfg, "no_sign", cx, cy, size / 200.0, t)


# ---------------------------------------------------------------------------
# Time-label badge (drawn as a pill with a clock icon)
# ---------------------------------------------------------------------------
def _draw_time_label(canvas, cfg, label: str, cx, cy, t, popin_t0):
    if t < popin_t0:
        return
    from whatif import REPO_ROOT
    tf = skia.Typeface.MakeFromFile(str(REPO_ROOT / cfg["captions"]["font_primary"])) \
        or skia.Typeface.MakeFromName(cfg["captions"]["font_fallback"], skia.FontStyle.Bold()) \
        or skia.Typeface.MakeDefault()
    font = skia.Font(tf, 46)
    tw = font.measureText(label)
    pad_x = 44.0
    pad_y = 20.0
    h = 80.0
    w = tw + pad_x * 2 + 50.0
    rect = skia.Rect.MakeXYWH(cx - w / 2.0, cy - h / 2.0, w, h)
    r = h / 2.0
    rrect = skia.RRect.MakeRectXY(rect, r, r)
    fill_rgb = cfg["colors"]["time_label_fill"]
    canvas.drawRRect(rrect, skia.Paint(AntiAlias=True, Color=skia.Color(*fill_rgb)))
    out = cfg["colors"]["time_label_outline"]
    canvas.drawRRect(rrect, skia.Paint(AntiAlias=True, Color=skia.Color(*out),
                                       Style=skia.Paint.kStroke_Style, StrokeWidth=6))
    props_mod.draw_icon(canvas, cfg, "clock", cx - w / 2.0 + 42.0, cy, 0.28, t)
    p = skia.Paint(AntiAlias=True, Color=skia.Color(255, 255, 255))
    canvas.drawString(label, cx - w / 2.0 + 78.0, cy + font.getSize() * 0.35, font, p)


# ---------------------------------------------------------------------------
# Template renderers
# ---------------------------------------------------------------------------
def _render_intro_prop(canvas, cfg, script, scene, cast_by_id, t, scene_start, caches):
    prop = (scene.get("props") or [{}])[0]
    _draw_prop(canvas, cfg, prop, cfg["video"]["width"] / 2.0,
               cfg["video"]["safe_top_px"] + 520,
               float(cfg["photos"]["card_px_single"]),
               t, scene_start + 0.1, caches)


def _render_timeline_step(canvas, cfg, script, scene, cast_by_id, t, scene_start, caches):
    _draw_time_label(canvas, cfg, scene["time_label"],
                     cfg["video"]["width"] / 2.0, cfg["video"]["safe_top_px"] + 90,
                     t, scene_start + 0.05)
    prop = (scene.get("props") or [{}])[0]
    _draw_prop(canvas, cfg, prop, cfg["video"]["width"] / 2.0,
               cfg["video"]["safe_top_px"] + 460,
               float(cfg["photos"]["card_px_single"]),
               t, scene_start + 0.2, caches)


def _render_crowd_react(canvas, cfg, script, scene, cast_by_id, t, scene_start, caches):
    _draw_time_label(canvas, cfg, scene["time_label"],
                     cfg["video"]["width"] / 2.0, cfg["video"]["safe_top_px"] + 90,
                     t, scene_start + 0.05)
    prop = (scene.get("props") or [{}])[0]
    _draw_prop(canvas, cfg, prop, cfg["video"]["width"] / 2.0,
               cfg["video"]["safe_top_px"] + 430,
               float(cfg["photos"]["card_px_dual"]),
               t, scene_start + 0.2, caches)


def _render_two_reactors(canvas, cfg, script, scene, cast_by_id, t, scene_start, caches):
    _draw_time_label(canvas, cfg, scene["time_label"],
                     cfg["video"]["width"] / 2.0, cfg["video"]["safe_top_px"] + 90,
                     t, scene_start + 0.05)
    prop = (scene.get("props") or [{}])[0]
    _draw_prop(canvas, cfg, prop, cfg["video"]["width"] / 2.0,
               cfg["video"]["safe_top_px"] + 430,
               float(cfg["photos"]["card_px_dual"]),
               t, scene_start + 0.2, caches)


def _render_two_props_compare(canvas, cfg, script, scene, cast_by_id, t, scene_start, caches):
    _draw_time_label(canvas, cfg, scene["time_label"],
                     cfg["video"]["width"] / 2.0, cfg["video"]["safe_top_px"] + 90,
                     t, scene_start + 0.05)
    props = scene.get("props") or []
    size = float(cfg["photos"]["card_px_dual"])
    xs = [cfg["video"]["width"] * 0.30, cfg["video"]["width"] * 0.70]
    for i, prop in enumerate(props[:2]):
        _draw_prop(canvas, cfg, prop, xs[i],
                   cfg["video"]["safe_top_px"] + 460, size,
                   t, scene_start + 0.2 + i * 0.15, caches)


def _render_big_number(canvas, cfg, script, scene, cast_by_id, t, scene_start, caches):
    _draw_time_label(canvas, cfg, scene["time_label"],
                     cfg["video"]["width"] / 2.0, cfg["video"]["safe_top_px"] + 90,
                     t, scene_start + 0.05)
    if scene.get("props"):
        _draw_prop(canvas, cfg, scene["props"][0],
                   cfg["video"]["width"] / 2.0,
                   cfg["video"]["safe_top_px"] + 430,
                   float(cfg["photos"]["card_px_dual"]),
                   t, scene_start + 0.2, caches)


_RENDERERS = {
    "intro_prop": _render_intro_prop,
    "timeline_step": _render_timeline_step,
    "crowd_react": _render_crowd_react,
    "two_reactors": _render_two_reactors,
    "two_props_compare": _render_two_props_compare,
    "big_number": _render_big_number,
}


def render_scene(canvas, cfg, script, scene, cast_by_id, t, scene_start, caches):
    template = (scene.get("scene_template") or "").lower()
    fn = _RENDERERS.get(template)
    if fn is None:
        _LOG.warning("Unknown scene_template %r; using intro_prop", template)
        fn = _RENDERERS["intro_prop"]
    fn(canvas, cfg, script, scene, cast_by_id, t, scene_start, caches)
    _draw_cast(canvas, cfg, script, scene, t, cast_by_id, scene_start)


def available() -> set[str]:
    return set(_TEMPLATES)