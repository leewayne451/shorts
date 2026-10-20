"""Drawn utility icons: question_mark, arrow, sparkle, no_sign, clock.

Public API:
  draw_icon(canvas, cfg, name, x, y, scale, t)
  available() -> set[str]
"""
from __future__ import annotations

import math
from typing import Any, Dict

import skia

from whatif import get_logger

_LOG = get_logger("whatif.render.props")


def _outline(cfg: Dict[str, Any], width: float) -> skia.Paint:
    white = cfg["colors"]["outline_white"]
    return skia.Paint(AntiAlias=True, Color=skia.Color(*white),
                      Style=skia.Paint.kStroke_Style, StrokeWidth=width,
                      StrokeCap=skia.Paint.kRound_Cap,
                      StrokeJoin=skia.Paint.kRound_Join)


def _fill(rgb) -> skia.Paint:
    return skia.Paint(AntiAlias=True, Color=skia.Color(int(rgb[0]), int(rgb[1]), int(rgb[2])))


def _draw_question_mark(canvas: skia.Canvas, cfg: Dict[str, Any], t: float) -> None:
    color = cfg["colors"]["icon_question_mark"]
    pen = skia.Paint(AntiAlias=True, Color=skia.Color(*color),
                     Style=skia.Paint.kStroke_Style, StrokeWidth=22,
                     StrokeCap=skia.Paint.kRound_Cap,
                     StrokeJoin=skia.Paint.kRound_Join)
    path = skia.Path()
    path.moveTo(-30, -35)
    path.cubicTo(-30, -80, 40, -80, 40, -30)
    path.cubicTo(40, -5, 5, 0, 5, 35)
    canvas.drawPath(path, pen)
    canvas.drawCircle(5, 65, 12, _fill(color))
    canvas.drawPath(path, _outline(cfg, 5))


def _draw_arrow(canvas: skia.Canvas, cfg: Dict[str, Any], t: float) -> None:
    color = cfg["colors"]["icon_arrow"]
    pen = skia.Paint(AntiAlias=True, Color=skia.Color(*color),
                     Style=skia.Paint.kStroke_Style, StrokeWidth=18,
                     StrokeCap=skia.Paint.kRound_Cap,
                     StrokeJoin=skia.Paint.kRound_Join)
    path = skia.Path()
    path.moveTo(-60, 0)
    path.lineTo(40, 0)
    path.moveTo(40, 0)
    path.lineTo(10, -30)
    path.moveTo(40, 0)
    path.lineTo(10, 30)
    canvas.drawPath(path, pen)
    canvas.drawPath(path, _outline(cfg, 4))


def _draw_sparkle(canvas: skia.Canvas, cfg: Dict[str, Any], t: float) -> None:
    color = cfg["colors"]["icon_sparkle"]
    fill = _fill(color)
    # Four-pointed star
    for dx, dy, s in ((0, 0, 1.0), (40, -30, 0.5), (-40, 20, 0.45), (30, 40, 0.4)):
        path = skia.Path()
        r_out = 55 * s
        r_in = 14 * s
        for i in range(8):
            ang = math.pi / 4 * i - math.pi / 2
            r = r_out if i % 2 == 0 else r_in
            px, py = dx + r * math.cos(ang), dy + r * math.sin(ang)
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        path.close()
        canvas.drawPath(path, fill)
        canvas.drawPath(path, _outline(cfg, 3))


def _draw_no_sign(canvas: skia.Canvas, cfg: Dict[str, Any], t: float) -> None:
    color = cfg["colors"]["icon_no_sign"]
    pen = skia.Paint(AntiAlias=True, Color=skia.Color(*color),
                     Style=skia.Paint.kStroke_Style, StrokeWidth=22,
                     StrokeCap=skia.Paint.kRound_Cap)
    canvas.drawCircle(0, 0, 60, pen)
    canvas.drawLine(-42, 42, 42, -42, pen)
    canvas.drawCircle(0, 0, 60, _outline(cfg, 5))


def _draw_clock(canvas: skia.Canvas, cfg: Dict[str, Any], t: float) -> None:
    color = cfg["colors"]["icon_clock"]
    pen = skia.Paint(AntiAlias=True, Color=skia.Color(*color),
                     Style=skia.Paint.kStroke_Style, StrokeWidth=12,
                     StrokeCap=skia.Paint.kRound_Cap)
    canvas.drawCircle(0, 0, 55, pen)
    canvas.drawLine(0, 0, 0, -32, pen)
    canvas.drawLine(0, 0, 22, 10, pen)
    canvas.drawCircle(0, 0, 55, _outline(cfg, 5))


_REGISTRY = {
    "question_mark": _draw_question_mark,
    "arrow": _draw_arrow,
    "sparkle": _draw_sparkle,
    "no_sign": _draw_no_sign,
    "clock": _draw_clock,
}


def available() -> set[str]:
    return set(_REGISTRY.keys())


def draw_icon(canvas: skia.Canvas, cfg: Dict[str, Any], name: str,
              x: float, y: float, scale: float, t: float) -> None:
    fn = _REGISTRY.get(name)
    if fn is None:
        _LOG.warning("Unknown icon %r; using question_mark", name)
        fn = _REGISTRY["question_mark"]
    canvas.save()
    canvas.translate(x, y)
    canvas.scale(scale, scale)
    fn(canvas, cfg, t)
    canvas.restore()