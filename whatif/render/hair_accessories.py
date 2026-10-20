"""Hair style, hair color, and accessory registries drawn in code.

Every hair style is drawn BEHIND the head (the head circle is drawn on top of it later by
characters.py). Accessories are drawn on top of the head/face.

Unknown values fall back to defaults (bob hair, glasses with default accessory color idx 0).
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

import skia

from whatif import get_logger

_LOG = get_logger("whatif.render.hair_accessories")

_HAIR_STYLES = ("bob", "ponytail", "short", "bun")
_ACCESSORIES = ("none", "glasses", "beanie", "bow_tie", "chef_hat")


def available_hair_styles() -> set[str]:
    return set(_HAIR_STYLES)


def available_accessories() -> set[str]:
    return set(_ACCESSORIES)


def _hair_color(cfg: Dict[str, Any], spec: Dict[str, Any]) -> Tuple[int, int, int]:
    palette = cfg["hair_colors"]
    idx = int(spec.get("hair_color_idx", 0)) % len(palette)
    c = palette[idx]
    return (int(c[0]), int(c[1]), int(c[2]))


def _acc_color(cfg: Dict[str, Any], spec: Dict[str, Any]) -> Tuple[int, int, int]:
    palette = cfg["accessory_colors"]
    idx = int(spec.get("accessory_color_idx", 0)) % len(palette)
    c = palette[idx]
    return (int(c[0]), int(c[1]), int(c[2]))


def _fill_paint(rgb: Tuple[int, int, int]) -> skia.Paint:
    p = skia.Paint(AntiAlias=True, Color=skia.Color(*rgb))
    return p


def _outline_paint(cfg: Dict[str, Any], width_scale: float = 0.7) -> skia.Paint:
    white = cfg["colors"]["outline_white"]
    return skia.Paint(AntiAlias=True, Color=skia.Color(*white),
                      Style=skia.Paint.kStroke_Style,
                      StrokeWidth=float(cfg["characters"]["outline_px"]) * width_scale,
                      StrokeCap=skia.Paint.kRound_Cap,
                      StrokeJoin=skia.Paint.kRound_Join)


# ---------------------------------------------------------------------------
# Hair styles — drawn BEHIND the head, head circle centered at (0, r)
# ---------------------------------------------------------------------------
def _style_bob(canvas: skia.Canvas, cfg: Dict[str, Any], color: Tuple[int, int, int],
               head_d: float) -> None:
    r = head_d / 2.0
    path = skia.Path()
    # Head-hugging cap that extends down the right side past the chin.
    path.moveTo(-r * 1.05, r * 0.9)
    path.cubicTo(-r * 1.2, -r * 0.4, -r * 0.6, -r * 1.15, 0.0, -r * 1.05)
    path.cubicTo(r * 0.7, -r * 1.05, r * 1.15, -r * 0.3, r * 1.05, r * 1.55)
    path.cubicTo(r * 0.95, r * 1.7, r * 0.6, r * 1.6, r * 0.55, r * 1.3)
    path.cubicTo(r * 0.6, r * 0.6, r * 0.5, 0.1, 0.1, 0.0)
    # Side-swept bangs across the forehead
    path.cubicTo(-r * 0.5, -r * 0.1, -r * 0.9, r * 0.2, -r * 0.9, r * 0.7)
    path.close()
    canvas.drawPath(path, _fill_paint(color))
    canvas.drawPath(path, _outline_paint(cfg))


def _style_short(canvas: skia.Canvas, cfg: Dict[str, Any], color: Tuple[int, int, int],
                 head_d: float) -> None:
    r = head_d / 2.0
    path = skia.Path()
    path.moveTo(-r * 1.05, r * 0.8)
    path.cubicTo(-r * 1.15, -r * 0.3, -r * 0.6, -r * 1.1, 0.0, -r * 1.05)
    path.cubicTo(r * 0.6, -r * 1.1, r * 1.1, -r * 0.4, r * 1.0, r * 0.6)
    path.lineTo(r * 0.75, r * 0.5)
    path.cubicTo(r * 0.7, 0.0, r * 0.4, -r * 0.2, 0.0, -r * 0.3)
    path.cubicTo(-r * 0.6, -r * 0.2, -r * 0.9, r * 0.2, -r * 0.9, r * 0.7)
    path.close()
    canvas.drawPath(path, _fill_paint(color))
    canvas.drawPath(path, _outline_paint(cfg))


def _style_ponytail(canvas: skia.Canvas, cfg: Dict[str, Any], color: Tuple[int, int, int],
                    head_d: float) -> None:
    r = head_d / 2.0
    # Cap
    cap = skia.Path()
    cap.moveTo(-r * 1.05, r * 0.85)
    cap.cubicTo(-r * 1.15, -r * 0.3, -r * 0.6, -r * 1.1, 0.0, -r * 1.05)
    cap.cubicTo(r * 0.6, -r * 1.1, r * 1.0, -r * 0.4, r * 0.95, r * 0.4)
    cap.cubicTo(r * 0.7, 0.0, r * 0.4, -r * 0.2, 0.0, -r * 0.3)
    cap.cubicTo(-r * 0.6, -r * 0.2, -r * 0.9, r * 0.3, -r * 0.9, r * 0.7)
    cap.close()
    # Ponytail bulge at the back-left (the character's left is negative x)
    tail = skia.Path()
    tx, ty = -r * 0.95, r * 0.1
    tail.moveTo(tx, ty)
    tail.cubicTo(tx - r * 0.35, ty + r * 0.4, tx - r * 0.45, ty + r * 1.0,
                 tx - r * 0.15, ty + r * 1.4)
    tail.cubicTo(tx + r * 0.15, ty + r * 1.2, tx + r * 0.15, ty + r * 0.4, tx, ty)
    tail.close()
    for p in (cap, tail):
        canvas.drawPath(p, _fill_paint(color))
        canvas.drawPath(p, _outline_paint(cfg))


def _style_bun(canvas: skia.Canvas, cfg: Dict[str, Any], color: Tuple[int, int, int],
               head_d: float) -> None:
    r = head_d / 2.0
    _style_short(canvas, cfg, color, head_d)
    # Bun circle above the crown
    bun_r = r * 0.35
    cx, cy = 0.0, -r * 1.05 - bun_r * 0.4
    canvas.drawCircle(cx, cy, bun_r, _fill_paint(color))
    canvas.drawCircle(cx, cy, bun_r, _outline_paint(cfg))


_HAIR_FN = {
    "bob": _style_bob,
    "short": _style_short,
    "ponytail": _style_ponytail,
    "bun": _style_bun,
}


def draw_hair_back(canvas: skia.Canvas, cfg: Dict[str, Any], spec: Dict[str, Any],
                   sick: bool = False) -> None:
    style = (spec.get("hair_style") or "bob").lower()
    fn = _HAIR_FN.get(style)
    if fn is None:
        _LOG.warning("Unknown hair_style %r; using bob", style)
        fn = _HAIR_FN["bob"]
    color = _hair_color(cfg, spec)
    if sick:
        g = cfg["colors"]["sick_green"]
        # Tint toward sick green, keep recognizable.
        color = (int((color[0] + g[0]) / 2), int((color[1] + g[1]) / 2),
                 int((color[2] + g[2]) / 2))
    fn(canvas, cfg, color, float(cfg["characters"]["head_diameter_px"]))


# ---------------------------------------------------------------------------
# Accessories — drawn on top of the head
# ---------------------------------------------------------------------------
def _acc_glasses(canvas: skia.Canvas, cfg: Dict[str, Any], head_d: float,
                 color: Tuple[int, int, int]) -> None:
    r = head_d / 2.0
    pen = skia.Paint(AntiAlias=True, Color=skia.Color(*color),
                     Style=skia.Paint.kStroke_Style,
                     StrokeWidth=head_d * 0.028,
                     StrokeCap=skia.Paint.kRound_Cap,
                     StrokeJoin=skia.Paint.kRound_Join)
    eye_dx = head_d * 0.16
    cy = r - head_d * 0.02
    lens_r = head_d * 0.11
    for sign in (-1, 1):
        cx = sign * eye_dx
        canvas.drawCircle(cx, cy, lens_r, pen)
    # Bridge
    canvas.drawLine(-eye_dx + lens_r, cy, eye_dx - lens_r, cy, pen)


def _acc_beanie(canvas: skia.Canvas, cfg: Dict[str, Any], head_d: float,
                color: Tuple[int, int, int]) -> None:
    r = head_d / 2.0
    cap = skia.Path()
    cap.moveTo(-r * 1.0, -r * 0.45)
    cap.cubicTo(-r * 1.0, -r * 1.25, r * 1.0, -r * 1.25, r * 1.0, -r * 0.45)
    cap.lineTo(r * 0.95, -r * 0.35)
    cap.lineTo(-r * 0.95, -r * 0.35)
    cap.close()
    canvas.drawPath(cap, _fill_paint(color))
    canvas.drawPath(cap, _outline_paint(cfg))
    # Pom-pom
    canvas.drawCircle(0.0, -r * 1.2, r * 0.13, _fill_paint(color))
    canvas.drawCircle(0.0, -r * 1.2, r * 0.13, _outline_paint(cfg))


def _acc_bow_tie(canvas: skia.Canvas, cfg: Dict[str, Any], head_d: float,
                 color: Tuple[int, int, int]) -> None:
    r = head_d / 2.0
    cy = r * 1.65  # just below the neck, on the body
    wing_w, wing_h = head_d * 0.18, head_d * 0.10
    p = skia.Path()
    p.moveTo(-wing_w * 0.2, cy)
    p.lineTo(-wing_w * 1.3, cy - wing_h)
    p.lineTo(-wing_w * 1.3, cy + wing_h)
    p.close()
    p.moveTo(wing_w * 0.2, cy)
    p.lineTo(wing_w * 1.3, cy - wing_h)
    p.lineTo(wing_w * 1.3, cy + wing_h)
    p.close()
    canvas.drawPath(p, _fill_paint(color))
    canvas.drawPath(p, _outline_paint(cfg))
    # Knot
    knot = skia.Rect.MakeXYWH(-head_d * 0.045, cy - head_d * 0.045,
                              head_d * 0.09, head_d * 0.09)
    canvas.drawRect(knot, _fill_paint(color))
    canvas.drawRect(knot, _outline_paint(cfg))


def _acc_chef_hat(canvas: skia.Canvas, cfg: Dict[str, Any], head_d: float,
                  color: Tuple[int, int, int]) -> None:
    r = head_d / 2.0
    base = skia.Rect.MakeXYWH(-r * 0.65, -r * 1.0, r * 1.3, r * 0.22)
    canvas.drawRect(base, _fill_paint(color))
    canvas.drawRect(base, _outline_paint(cfg))
    # Puffy top from three overlapping circles
    for dx in (-r * 0.4, 0.0, r * 0.4):
        canvas.drawCircle(dx, -r * 1.05, r * 0.35, _fill_paint(color))
    for dx in (-r * 0.4, 0.0, r * 0.4):
        canvas.drawCircle(dx, -r * 1.05, r * 0.35, _outline_paint(cfg))


_ACC_FN = {
    "none": None,
    "glasses": _acc_glasses,
    "beanie": _acc_beanie,
    "bow_tie": _acc_bow_tie,
    "chef_hat": _acc_chef_hat,
}


def draw_accessory(canvas: skia.Canvas, cfg: Dict[str, Any], spec: Dict[str, Any]) -> None:
    acc = (spec.get("accessory") or "none").lower()
    fn = _ACC_FN.get(acc)
    if acc not in _ACC_FN:
        _LOG.warning("Unknown accessory %r; using none", acc)
        return
    if fn is None:
        return
    color = _acc_color(cfg, spec)
    fn(canvas, cfg, float(cfg["characters"]["head_diameter_px"]), color)