"""Per-beat caption line drawing (Poppins Bold).

One caption per beat, displayed at once with a pop-in. Emphasis words get colored
(yellow for `emphasis`, orange for `caption_secondary`), others white, all with a soft shadow.

Public API:
  layout_line(text, emphasis, cfg) -> list[WordPlacement]
  draw_caption_line(canvas, cfg, placements, x, y, popin_t0, t, anchor="center")
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import skia

from whatif import get_logger

_LOG = get_logger("whatif.render.captions")


@dataclass
class WordPlacement:
    word: str
    x: float     # relative to anchor point
    y: float
    width: float
    color: Tuple[int, int, int]


def _load_typeface(cfg: Dict[str, Any]) -> skia.Typeface:
    from whatif import REPO_ROOT
    primary = REPO_ROOT / cfg["captions"]["font_primary"]
    if primary.is_file():
        tf = skia.Typeface.MakeFromFile(str(primary))
        if tf is not None:
            return tf
    tf = skia.Typeface.MakeFromName(cfg["captions"]["font_fallback"], skia.FontStyle.Bold())
    if tf is None:
        tf = skia.Typeface.MakeDefault()
    if tf is None:
        raise RuntimeError("No usable typeface found for captions.")
    return tf


def _color_for(word: str, emphasis: List[str], cfg: Dict[str, Any]) -> Tuple[int, int, int]:
    wl = word.strip().lower().strip(".,!?;:")
    emp = {e.strip().lower() for e in emphasis}
    if wl in emp:
        return tuple(cfg["colors"]["caption_active"])
    if wl in {e.strip().lower() for e in (cfg.get("_secondary_emphasis") or [])}:
        return tuple(cfg["colors"]["caption_secondary"])
    return tuple(cfg["colors"]["caption_white"])


def layout_line(text: str, emphasis: List[str], cfg: Dict[str, Any]) -> List[WordPlacement]:
    """Lay out words on a single line, wrapping to at most cfg["captions"]["max_lines"]."""
    tf = _load_typeface(cfg)
    size = 68
    font = skia.Font(tf, size)
    space_w = font.measureText(" ")
    max_chars = int(cfg["captions"]["max_chars_per_line"])
    max_lines = int(cfg["captions"]["max_lines"])

    words = text.split()
    lines: List[List[str]] = [[]]
    cur_len = 0
    for w in words:
        if lines[-1] and cur_len + 1 + len(w) > max_chars and len(lines) < max_lines:
            lines.append([])
            cur_len = 0
        lines[-1].append(w)
        cur_len += len(w) + 1

    # Even if >max_lines, we clamp: append remaining to last line (readable enough).
    while len(lines) > max_lines:
        last = lines.pop()
        lines[-1].extend(last)

    line_h = size * 1.25
    total_h = len(lines) * line_h
    placements: List[WordPlacement] = []
    for li, line in enumerate(lines):
        line_text = " ".join(line)
        line_w = font.measureText(line_text)
        x = -line_w / 2.0
        y = li * line_h - total_h / 2.0 + size * 0.8
        for wi, word in enumerate(line):
            ww = font.measureText(word)
            color = _color_for(word, emphasis, cfg)
            placements.append(WordPlacement(word=word, x=x + ww / 2.0, y=y, width=ww, color=color))
            x += ww
            if wi != len(line) - 1:
                x += space_w
    return placements


def draw_caption_line(
    canvas: skia.Canvas,
    cfg: Dict[str, Any],
    placements: List[WordPlacement],
    cx: float,
    cy: float,
    popin_t0: float,
    t: float,
) -> None:
    """Draw the whole line with pop-in and a soft shadow. Center at (cx,cy)."""
    if not placements:
        return
    if t < popin_t0:
        return
    elapsed = t - popin_t0
    dur = 0.25
    if elapsed < dur:
        u = elapsed / dur
        c1 = 1.70158
        c3 = c1 + 1.0
        eased = 1.0 + c3 * (u - 1) ** 3 + c1 * (u - 1) ** 2
        scale = 0.7 + 0.3 * eased
    else:
        scale = 1.0

    tf = _load_typeface(cfg)
    font = skia.Font(tf, 68)
    font.setSubpixel(True)

    shadow = cfg["colors"]["caption_shadow"]
    shadow_off = float(cfg["captions"]["shadow_offset_px"])

    canvas.save()
    canvas.translate(cx, cy)
    canvas.scale(scale, scale)
    for p in placements:
        # shadow
        sp = skia.Paint(AntiAlias=True, Color=skia.Color(shadow[0], shadow[1], shadow[2], shadow[3]))
        canvas.drawString(p.word, p.x - p.width / 2.0 + shadow_off,
                          p.y + shadow_off, font, sp)
        # main
        mp = skia.Paint(AntiAlias=True, Color=skia.Color(*p.color))
        canvas.drawString(p.word, p.x - p.width / 2.0, p.y, font, mp)
    canvas.restore()


def caption_appears(placements: List[WordPlacement], needle: str) -> bool:
    """Case-insensitive token check used by engine's captions_audit."""
    return needle.lower() in " ".join(p.word for p in placements).lower()