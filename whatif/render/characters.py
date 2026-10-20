"""Emoji-style hands drawn in code, driven by a shared helper set (rounded finger capsule,
palm blob, thumb). Registry of exactly 8 hands. Each hand is drawn in local space where the
wrist is at (0,0) and the fingers point along -Y (up) unless rotated by the caller.

Public API:
  draw_hand(canvas, cfg, name, x, y, scale, rotation_deg, t)
  available() -> set[str]
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple

import skia

from whatif import get_logger

_LOG = get_logger("whatif.render.hands")


def _palette(cfg: Dict[str, Any]) -> Tuple[Tuple[int, int, int], Tuple[int, int, int], Tuple[int, int, int]]:
    fill = tuple(cfg["colors"]["hand_fill"])
    outline = tuple(cfg["colors"]["hand_outline"])
    highlight = tuple(cfg["colors"]["hand_highlight"])
    return (fill, outline, highlight)


# ---------------------------------------------------------------------------
# Shared drawing helpers
# ---------------------------------------------------------------------------
def _filled_blob(canvas: skia.Canvas, path: skia.Path,
                 fill: Tuple[int, int, int], outline: Tuple[int, int, int],
                 stroke_w: float) -> None:
    canvas.drawPath(path, skia.Paint(AntiAlias=True, Color=skia.Color(*fill)))
    p = skia.Paint(AntiAlias=True, Color=skia.Color(*outline),
                   Style=skia.Paint.kStroke_Style, StrokeWidth=stroke_w,
                   StrokeCap=skia.Paint.kRound_Cap, StrokeJoin=skia.Paint.kRound_Join)
    canvas.drawPath(path, p)


def _palm(cfg: Dict[str, Any], w: float, h: float) -> skia.Path:
    fill, _, _ = _palette(cfg)
    # Rounded rectangle palm, slightly wider at the knuckles.
    p = skia.Path()
    r = min(w, h) * 0.35
    p.addRRect(skia.RRect.MakeRectXY(
        skia.Rect.MakeXYWH(-w / 2.0, -h, w, h), r, r
    ))
    return p


def _finger_capsule(cfg: Dict[str, Any], base_x: float, base_y: float,
                    length: float, width: float) -> skia.Path:
    """Vertical capsule starting at (base_x, base_y) and extending up by `length`."""
    p = skia.Path()
    p.addRRect(skia.RRect.MakeRectXY(
        skia.Rect.MakeXYWH(base_x - width / 2.0, base_y - length, width, length),
        width / 2.0, width / 2.0
    ))
    return p


def _thumb(cfg: Dict[str, Any], base_x: float, base_y: float,
           length: float, width: float, angle_deg: float) -> skia.Path:
    p = skia.Path()
    p.addRRect(skia.RRect.MakeRectXY(
        skia.Rect.MakeXYWH(-width / 2.0, -length, width, length),
        width / 2.0, width / 2.0
    ))
    m = skia.Matrix()
    m.setRotate(angle_deg)
    m.postTranslate(base_x, base_y)
    p.transform(m)
    return p


def _draw_four_fingers(canvas: skia.Canvas, cfg: Dict[str, Any],
                       base_y: float, fingers_up_lengths: list[float],
                       palm_w: float, finger_w: float, stroke_w: float) -> None:
    fill, outline, _ = _palette(cfg)
    n = len(fingers_up_lengths)
    total = palm_w * 0.78
    step = total / max(1, n - 1)
    x0 = -total / 2.0
    for i, length in enumerate(fingers_up_lengths):
        bx = x0 + i * step
        cap = _finger_capsule(cfg, bx, base_y, length, finger_w)
        _filled_blob(canvas, cap, fill, outline, stroke_w)


# ---------------------------------------------------------------------------
# Individual hands (local space: wrist at (0,0), up is -Y)
# ---------------------------------------------------------------------------
def _hand_open_palm(canvas: skia.Canvas, cfg: Dict[str, Any], t: float) -> None:
    fill, outline, _ = _palette(cfg)
    palm_w, palm_h = 90.0, 95.0
    finger_w = 20.0
    stroke_w = 6.0
    base_y = -palm_h
    _draw_four_fingers(canvas, cfg, base_y,
                       [70.0, 82.0, 78.0, 62.0], palm_w, finger_w, stroke_w)
    # Thumb out to the left
    thumb = _thumb(cfg, -palm_w * 0.48, -palm_h * 0.35, 55.0, 20.0, 32.0)
    _filled_blob(canvas, thumb, fill, outline, stroke_w)
    _filled_blob(canvas, _palm(cfg, palm_w, palm_h), fill, outline, stroke_w)


def _hand_point_right(canvas: skia.Canvas, cfg: Dict[str, Any], t: float) -> None:
    canvas.save()
    canvas.rotate(-90.0)  # reuse the point_up hand and rotate it 90° right
    _hand_point_up(canvas, cfg, t)
    canvas.restore()


def _hand_point_left(canvas: skia.Canvas, cfg: Dict[str, Any], t: float) -> None:
    canvas.save()
    canvas.rotate(90.0)
    _hand_point_up(canvas, cfg, t)
    canvas.restore()


def _hand_point_up(canvas: skia.Canvas, cfg: Dict[str, Any], t: float) -> None:
    fill, outline, _ = _palette(cfg)
    palm_w, palm_h = 78.0, 80.0
    stroke_w = 6.0
    base_y = -palm_h
    # Index finger fully up, others curled (short)
    _draw_four_fingers(canvas, cfg, base_y,
                       [95.0, 30.0, 28.0, 26.0], palm_w, 20.0, stroke_w)
    thumb = _thumb(cfg, -palm_w * 0.45, -palm_h * 0.35, 55.0, 20.0, 40.0)
    _filled_blob(canvas, thumb, fill, outline, stroke_w)
    _filled_blob(canvas, _palm(cfg, palm_w, palm_h), fill, outline, stroke_w)


def _hand_wave(canvas: skia.Canvas, cfg: Dict[str, Any], t: float) -> None:
    # Open palm rotated slightly by a sine wave
    canvas.save()
    canvas.rotate(math.sin(t * 6.0) * 12.0)
    _hand_open_palm(canvas, cfg, t)
    canvas.restore()


def _hand_pinch(canvas: skia.Canvas, cfg: Dict[str, Any], t: float) -> None:
    fill, outline, _ = _palette(cfg)
    palm_w, palm_h = 74.0, 78.0
    stroke_w = 6.0
    base_y = -palm_h
    _draw_four_fingers(canvas, cfg, base_y,
                       [55.0, 52.0, 50.0, 40.0], palm_w, 20.0, stroke_w)
    # Thumb curled up and inward to "pinch"
    thumb = _thumb(cfg, -palm_w * 0.30, -palm_h * 0.55, 50.0, 18.0, 70.0)
    _filled_blob(canvas, thumb, fill, outline, stroke_w)
    _filled_blob(canvas, _palm(cfg, palm_w, palm_h), fill, outline, stroke_w)


def _hand_thumbs_up(canvas: skia.Canvas, cfg: Dict[str, Any], t: float) -> None:
    fill, outline, _ = _palette(cfg)
    palm_w, palm_h = 82.0, 84.0
    stroke_w = 6.0
    base_y = -palm_h
    _draw_four_fingers(canvas, cfg, base_y,
                       [26.0, 26.0, 26.0, 24.0], palm_w, 20.0, stroke_w)
    # Thumb long up
    thumb = _thumb(cfg, -palm_w * 0.20, -palm_h * 0.85, 75.0, 22.0, 0.0)
    _filled_blob(canvas, thumb, fill, outline, stroke_w)
    _filled_blob(canvas, _palm(cfg, palm_w, palm_h), fill, outline, stroke_w)


def _hand_palm_up(canvas: skia.Canvas, cfg: Dict[str, Any], t: float) -> None:
    # Like open_palm, but flipped vertically and flattened (presenting a flat palm).
    canvas.save()
    canvas.scale(1.0, -0.9)
    _hand_open_palm(canvas, cfg, t)
    canvas.restore()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
_REGISTRY = {
    "point_up": _hand_point_up,
    "point_right": _hand_point_right,
    "point_left": _hand_point_left,
    "open_palm": _hand_open_palm,
    "wave": _hand_wave,
    "pinch": _hand_pinch,
    "thumbs_up": _hand_thumbs_up,
    "palm_up": _hand_palm_up,
}


def available() -> set[str]:
    return set(_REGISTRY.keys())


def draw_hand(
    canvas: skia.Canvas,
    cfg: Dict[str, Any],
    name: str,
    x: float,
    y: float,
    scale: float,
    rotation_deg: float,
    t: float,
) -> None:
    fn = _REGISTRY.get(name)
    if fn is None:
        _LOG.warning("Unknown hand %r; falling back to open_palm", name)
        fn = _REGISTRY["open_palm"]
    canvas.save()
    canvas.translate(x, y)
    canvas.rotate(rotation_deg)
    canvas.scale(scale, scale)
    fn(canvas, cfg, t)
    canvas.restore()