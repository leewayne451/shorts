"""Character drawing: head, body (with optional bust bumps), faces, brows, poses,
sick/horror reaction.

All shapes are drawn with skia-python. Colors come from config.yaml. Coordinates are in the
local character space where (0,0) is the top-center of the head, and the body hangs below.

Public API:
  draw_character(canvas, cfg, spec, x, y, scale, t, pose, face, sick, bench_alpha)
  body_path(cfg, spec) -> skia.Path  (used by tests to check bust-vs-no-bust differ)
  head_bounds(cfg) -> dict
  hands_anchor(cfg, spec) -> dict
"""
from __future__ import annotations

import math
from typing import Any, Dict, Tuple

import skia

from whatif import get_logger

_LOG = get_logger("whatif.render.characters")

_FACES = {"smile", "grin", "open", "meh", "ew", "brows_angry", "brows_raised",
          "brows_worried", "brows_flat"}
_POSES = {"idle", "present", "point", "pinch", "shrug", "think", "wave", "celebrate"}


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------
def head_bounds(cfg: Dict[str, Any]) -> Dict[str, float]:
    head_d = float(cfg["characters"]["head_diameter_px"])
    head_r = head_d / 2.0
    body_h = head_d * float(cfg["characters"]["body_height_ratio"])
    total_h = head_d + body_h
    return {
        "head_d": head_d,
        "head_r": head_r,
        "body_h": body_h,
        "total_h": total_h,
        "total_w": head_d * 1.1,
    }


# ---------------------------------------------------------------------------
# Body path (with optional bust bumps)
# ---------------------------------------------------------------------------
def _bust_bump_radius(head_d: float, bust_size: float) -> float:
    return max(0.0, head_d * 0.055 * bust_size)


def body_path(cfg: Dict[str, Any], spec: Dict[str, Any]) -> skia.Path:
    """Build the body outline path. If spec['bust'] is False or bust_size==0, plain tapered body."""
    head_d = float(cfg["characters"]["head_diameter_px"])
    neck_ratio = float(cfg["characters"]["body_neck_ratio"])
    base_ratio = float(cfg["characters"]["body_base_ratio"])
    body_h = head_d * float(cfg["characters"]["body_height_ratio"])
    bust_size = float(cfg["characters"]["bust_size"])
    want_bust = bool(spec.get("bust", True)) and bust_size > 0.0

    neck_w = head_d * neck_ratio
    base_w = head_d * base_ratio
    cx = 0.0
    top_y = head_d * 0.6
    bot_y = top_y + body_h

    path = skia.Path()
    path.moveTo(cx - neck_w / 2.0, top_y)

    if want_bust:
        r = _bust_bump_radius(head_d, bust_size)
        bump_center_y = top_y + body_h * 0.22
        left_neck_x = cx - neck_w / 2.0
        left_base_x = cx - base_w / 2.0
        t = (bump_center_y - top_y) / body_h
        straight_x = left_neck_x + (left_base_x - left_neck_x) * t
        bump_x = straight_x - r
        path.cubicTo(
            left_neck_x + (straight_x - left_neck_x) * 0.5, bump_center_y - r * 1.6,
            bump_x - r * 0.2, bump_center_y - r * 0.9,
            bump_x, bump_center_y,
        )
        path.cubicTo(
            bump_x - r * 0.2, bump_center_y + r * 0.9,
            left_neck_x + (straight_x - left_neck_x) * 0.6, bump_center_y + r * 1.6,
            straight_x, bump_center_y + r * 1.4,
        )
    path.lineTo(cx - base_w / 2.0, bot_y - head_d * 0.05)
    path.quadTo(cx - base_w / 2.0, bot_y, cx - base_w / 2.0 + head_d * 0.05, bot_y)
    path.lineTo(cx + base_w / 2.0 - head_d * 0.05, bot_y)
    path.quadTo(cx + base_w / 2.0, bot_y, cx + base_w / 2.0, bot_y - head_d * 0.05)

    if want_bust:
        r = _bust_bump_radius(head_d, bust_size)
        right_neck_x = cx + neck_w / 2.0
        right_base_x = cx + base_w / 2.0
        bump_center_y = top_y + body_h * 0.22
        t = (bump_center_y - top_y) / body_h
        straight_x = right_neck_x + (right_base_x - right_neck_x) * t
        bump_x = straight_x + r
        path.cubicTo(
            right_neck_x + (straight_x - right_neck_x) * 0.6, bump_center_y + r * 1.6,
            bump_x + r * 0.2, bump_center_y + r * 0.9,
            bump_x, bump_center_y,
        )
        path.cubicTo(
            bump_x + r * 0.2, bump_center_y - r * 0.9,
            right_neck_x + (straight_x - right_neck_x) * 0.5, bump_center_y - r * 1.6,
            straight_x, bump_center_y - r * 1.4,
        )

    path.lineTo(cx + neck_w / 2.0, top_y)
    path.close()
    return path


# ---------------------------------------------------------------------------
# Drawing primitives
# ---------------------------------------------------------------------------
def _paint_fill(rgb: Tuple[int, int, int]) -> skia.Paint:
    p = skia.Paint(AntiAlias=True)
    p.setColor(skia.Color(int(rgb[0]), int(rgb[1]), int(rgb[2])))
    p.setStyle(skia.Paint.kFill_Style)
    return p


def _paint_stroke_white(cfg: Dict[str, Any], width_scale: float = 1.0) -> skia.Paint:
    white = cfg["colors"]["outline_white"]
    p = skia.Paint(AntiAlias=True)
    p.setColor(skia.Color(white[0], white[1], white[2]))
    p.setStyle(skia.Paint.kStroke_Style)
    p.setStrokeWidth(float(cfg["characters"]["outline_px"]) * width_scale)
    p.setStrokeCap(skia.Paint.kRound_Cap)
    p.setStrokeJoin(skia.Paint.kRound_Join)
    return p


def _tint_outline_paint(cfg: Dict[str, Any], sick: bool, width_scale: float = 1.0) -> skia.Paint:
    p = _paint_stroke_white(cfg, width_scale)
    if sick:
        g = cfg["colors"]["sick_green"]
        p.setColor(skia.Color(g[0], g[1], g[2]))
    return p


def _hair_color(cfg: Dict[str, Any], spec: Dict[str, Any]) -> Tuple[int, int, int]:
    palette = cfg["hair_colors"]
    idx = int(spec.get("hair_color_idx", 0)) % len(palette)
    c = palette[idx]
    return (int(c[0]), int(c[1]), int(c[2]))


# ---------------------------------------------------------------------------
# Head + hair + face
# ---------------------------------------------------------------------------
def _draw_hair_back(canvas: skia.Canvas, cfg: Dict[str, Any], spec: Dict[str, Any],
                    sick: bool) -> None:
    from whatif.render import hair_accessories as ha
    ha.draw_hair_back(canvas, cfg, spec, sick=sick)


def _draw_head(canvas: skia.Canvas, cfg: Dict[str, Any], spec: Dict[str, Any],
               sick: bool) -> None:
    head_d = float(cfg["characters"]["head_diameter_px"])
    r = head_d / 2.0
    fill = _paint_fill(tuple(cfg["colors"]["character_fill"]))
    stroke = _tint_outline_paint(cfg, sick)
    canvas.drawCircle(0.0, r, r, fill)
    canvas.drawCircle(0.0, r, r - stroke.getStrokeWidth() / 2.0, stroke)


def _draw_face(canvas: skia.Canvas, cfg: Dict[str, Any], spec: Dict[str, Any],
               face: str, sick: bool, blink: bool) -> None:
    if face not in _FACES:
        face = "smile"
    head_d = float(cfg["characters"]["head_diameter_px"])
    r = head_d / 2.0
    cx, cy = 0.0, r

    white = (255, 255, 255)
    if sick:
        g = cfg["colors"]["sick_green"]
        white = (g[0], g[1], g[2])

    eye_dx = head_d * 0.16
    eye_y = cy - head_d * 0.02
    eye_r = head_d * 0.045
    if face == "ew":
        pen = skia.Paint(AntiAlias=True, Color=skia.Color(*white),
                         Style=skia.Paint.kStroke_Style,
                         StrokeWidth=head_d * 0.028,
                         StrokeCap=skia.Paint.kRound_Cap)
        for sign in (-1, 1):
            lx = cx + sign * eye_dx
            canvas.drawLine(lx - eye_r * 1.4, eye_y - eye_r, lx + eye_r * 0.6, eye_y, pen)
            canvas.drawLine(lx - eye_r * 1.4, eye_y + eye_r, lx + eye_r * 0.6, eye_y, pen)
    else:
        pen = skia.Paint(AntiAlias=True, Color=skia.Color(*white),
                         Style=skia.Paint.kFill_Style)
        if blink:
            spen = skia.Paint(AntiAlias=True, Color=skia.Color(*white),
                              Style=skia.Paint.kStroke_Style,
                              StrokeWidth=head_d * 0.022,
                              StrokeCap=skia.Paint.kRound_Cap)
            for sign in (-1, 1):
                lx = cx + sign * eye_dx
                canvas.drawLine(lx - eye_r, eye_y, lx + eye_r, eye_y, spen)
        else:
            for sign in (-1, 1):
                canvas.drawCircle(cx + sign * eye_dx, eye_y, eye_r, pen)

    if face in ("brows_angry", "brows_raised", "brows_worried", "brows_flat"):
        _draw_brows(canvas, cfg, face, cx, cy, head_d, white)

    mouth_pen = skia.Paint(AntiAlias=True, Color=skia.Color(*white),
                           Style=skia.Paint.kStroke_Style,
                           StrokeWidth=head_d * 0.032,
                           StrokeCap=skia.Paint.kRound_Cap)
    mouth_fill = skia.Paint(AntiAlias=True, Color=skia.Color(*white),
                            Style=skia.Paint.kFill_Style)
    my = cy + head_d * 0.18
    mw = head_d * 0.22

    if face in ("smile", "brows_angry", "brows_raised", "brows_worried", "brows_flat"):
        path = skia.Path()
        path.moveTo(cx - mw, my)
        path.quadTo(cx, my + head_d * 0.14, cx + mw, my - head_d * 0.02)
        canvas.drawPath(path, mouth_pen)
    elif face == "grin":
        rect = skia.Rect.MakeLTRB(cx - mw, my - head_d * 0.04, cx + mw, my + head_d * 0.14)
        canvas.drawArc(rect, 0.0, 180.0, False, mouth_pen)
    elif face == "open":
        canvas.drawCircle(cx, my + head_d * 0.02, head_d * 0.09, mouth_fill)
    elif face == "meh":
        canvas.drawLine(cx - mw, my, cx + mw, my, mouth_pen)
    elif face == "ew":
        path = skia.Path()
        path.moveTo(cx - mw, my)
        step = (mw * 2.0) / 6.0
        amp = head_d * 0.03
        for i in range(1, 7):
            y = my + (amp if i % 2 == 0 else -amp)
            path.lineTo(cx - mw + i * step, y)
        canvas.drawPath(path, mouth_pen)


def _draw_brows(canvas: skia.Canvas, cfg: Dict[str, Any], face: str,
                cx: float, cy: float, head_d: float, white: Tuple[int, int, int]) -> None:
    pen = skia.Paint(AntiAlias=True, Color=skia.Color(*white),
                     Style=skia.Paint.kStroke_Style,
                     StrokeWidth=head_d * 0.025,
                     StrokeCap=skia.Paint.kRound_Cap)
    by = cy - head_d * 0.18
    brow_len = head_d * 0.10
    eye_dx = head_d * 0.16

    for sign in (-1, 1):
        cx_eye = cx + sign * eye_dx
        if face == "brows_angry":
            inner = (cx_eye - sign * brow_len, by + head_d * 0.03)
            outer = (cx_eye + sign * brow_len, by - head_d * 0.03)
        elif face == "brows_raised":
            inner = (cx_eye - sign * brow_len, by - head_d * 0.03)
            outer = (cx_eye + sign * brow_len, by - head_d * 0.03)
        elif face == "brows_worried":
            inner = (cx_eye - sign * brow_len, by - head_d * 0.02)
            outer = (cx_eye + sign * brow_len, by + head_d * 0.03)
        else:
            inner = (cx_eye - sign * brow_len, by)
            outer = (cx_eye + sign * brow_len, by)
        canvas.drawLine(inner[0], inner[1], outer[0], outer[1], pen)


def _blink_state(cfg: Dict[str, Any], t: float, seed: float) -> bool:
    lo, hi = cfg["characters"]["blink_every_seconds"]
    period = (lo + hi) / 2.0
    phase = (t + seed) % period
    return phase < 0.12


# ---------------------------------------------------------------------------
# Poses + idle sway
# ---------------------------------------------------------------------------
_POSE_TILT = {
    "idle": 0.0, "present": -2.0, "point": 3.0, "pinch": -3.0,
    "shrug": 0.0, "think": 2.0, "wave": -1.5, "celebrate": 0.0,
}


def _idle_sway_deg(cfg: Dict[str, Any], t: float, seed: float) -> float:
    base = float(cfg["characters"]["tilt_degrees"])
    return base * math.sin(2 * math.pi * 0.15 * t + seed)


# ---------------------------------------------------------------------------
# Sick / horror effects
# ---------------------------------------------------------------------------
def _draw_sick_effects(canvas: skia.Canvas, cfg: Dict[str, Any], head_d: float, t: float) -> None:
    g = cfg["colors"]["sick_green"]
    pen = skia.Paint(AntiAlias=True, Color=skia.Color(g[0], g[1], g[2]),
                     Style=skia.Paint.kStroke_Style,
                     StrokeWidth=head_d * 0.02,
                     StrokeCap=skia.Paint.kRound_Cap)
    for k in range(3):
        base_x = -head_d * 0.62 - k * head_d * 0.06
        y0 = head_d * 0.25 + k * head_d * 0.15
        path = skia.Path()
        path.moveTo(base_x, y0)
        phase = t * 4.0 + k
        for i in range(6):
            x = base_x - i * head_d * 0.02
            y = y0 - i * head_d * 0.03 + math.sin(phase + i) * head_d * 0.02
            path.lineTo(x, y)
        canvas.drawPath(path, pen)
    drop_fill = skia.Paint(AntiAlias=True, Color=skia.Color(180, 220, 255))
    for k in range(2):
        dx = head_d * 0.66 + k * head_d * 0.06
        dy = head_d * 0.20 + k * head_d * 0.22 + math.sin(t * 3.0 + k) * head_d * 0.01
        path = skia.Path()
        r = head_d * 0.045
        path.moveTo(dx, dy - r)
        path.cubicTo(dx + r, dy, dx + r, dy + r, dx, dy + r)
        path.cubicTo(dx - r, dy + r, dx - r, dy, dx, dy - r)
        canvas.drawPath(path, drop_fill)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def draw_character(
    canvas: skia.Canvas,
    cfg: Dict[str, Any],
    spec: Dict[str, Any],
    x: float,
    y: float,
    scale: float,
    t: float,
    pose: str = "idle",
    face: str = "smile",
    sick: bool = False,
    bench_alpha: float = 1.0,
) -> None:
    """Draw a full character at (x,y) — (x,y) is the top-center of the head in canvas space."""
    if pose not in _POSES:
        pose = "idle"
    if face not in _FACES:
        face = "smile"
    if bench_alpha <= 0.01:
        return

    seed = (hash(spec.get("id", "c")) % 1000) / 1000.0
    blink = _blink_state(cfg, t, seed)

    pose_tilt = _POSE_TILT.get(pose, 0.0)
    sway = _idle_sway_deg(cfg, t, seed)
    angle = pose_tilt + sway

    canvas.save()
    canvas.translate(x, y)
    canvas.scale(scale, scale)
    canvas.rotate(angle)

    if bench_alpha < 0.999:
        canvas.saveLayerAlpha(None, int(255 * bench_alpha))

    _draw_hair_back(canvas, cfg, spec, sick)

    bp = body_path(cfg, spec)
    canvas.drawPath(bp, _paint_fill(tuple(cfg["colors"]["character_fill"])))
    canvas.drawPath(bp, _tint_outline_paint(cfg, sick))

    _draw_head(canvas, cfg, spec, sick)
    _draw_face(canvas, cfg, spec, face, sick, blink)

    from whatif.render import hair_accessories as ha
    ha.draw_accessory(canvas, cfg, spec)

    if sick:
        _draw_sick_effects(canvas, cfg, float(cfg["characters"]["head_diameter_px"]), t)

    if bench_alpha < 0.999:
        canvas.restore()

    canvas.restore()


def hands_anchor(cfg: Dict[str, Any], spec: Dict[str, Any]) -> Dict[str, Tuple[float, float]]:
    """Return anchor points for left/right hands in the character's local coordinate space."""
    head_d = float(cfg["characters"]["head_diameter_px"])
    body_h = head_d * float(cfg["characters"]["body_height_ratio"])
    chest_y = head_d * 0.6 + body_h * 0.45
    side_x = head_d * 0.75
    return {
        "left": (-side_x, chest_y),
        "right": (side_x, chest_y),
    }