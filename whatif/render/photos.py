"""Pixabay photo fetch, disk cache, credits, and framed-card drawing.

Public API:
  fetch_photo(query, cfg, cache_dir) -> PhotoResult | None
  load_image_skia(data: bytes) -> skia.Image | None
  center_crop_square(img) -> skia.Image
  draw_card(canvas, cfg, img, cx, cy, size_px, outline_px, t, popin_t0, popin_duration)

Sampling uses skia.Paint.setFilterQuality for compatibility across skia-python
versions (kLow_FilterQuality is available on all 80+ releases; SamplingOptions is not).
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import skia

from whatif import get_logger

_LOG = get_logger("whatif.render.photos")

_PIXABAY_URL = "https://pixabay.com/api/"


@dataclass
class PhotoResult:
    query: str
    slug: str
    image_bytes: bytes
    user: str
    page_url: str
    image_url: str
    cached: bool


def _slug(query: str) -> str:
    s = query.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "photo"


def _cache_paths(cache_dir: Path, slug: str) -> tuple[Path, Path]:
    return (cache_dir / f"{slug}.bin", cache_dir / f"{slug}.json")


def _pixabay_search(query: str, cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if not key:
        _LOG.warning("PIXABAY_API_KEY not set; falling back to question_mark icon.")
        return None
    pcfg = cfg["photos"]
    params = {
        "key": key,
        "q": query,
        "image_type": "photo",
        "safesearch": "true",
        "per_page": int(pcfg["per_page"]),
    }
    timeout = float(pcfg["timeout_seconds"])
    retries = int(pcfg["max_retries"])
    base = float(pcfg["backoff_base_seconds"])

    for attempt in range(retries + 1):
        try:
            r = requests.get(_PIXABAY_URL, params=params, timeout=timeout)
        except requests.RequestException as e:
            _LOG.warning("Pixabay request error: %s", e)
            time.sleep(base * (2 ** attempt))
            continue
        if r.status_code == 429:
            wait = 5.0 * (2 ** attempt)
            _LOG.warning("Pixabay 429; waiting %.1fs", wait)
            time.sleep(wait)
            continue
        if r.status_code >= 400:
            _LOG.warning("Pixabay HTTP %d: %s", r.status_code, r.text[:200])
            return None
        try:
            return r.json()
        except ValueError:
            return None
    return None


def _pick_hit(data: Dict[str, Any], min_width: int) -> Optional[Dict[str, Any]]:
    hits = data.get("hits") or []
    for h in hits:
        if int(h.get("imageWidth") or 0) >= min_width:
            return h
    return hits[0] if hits else None


def fetch_photo(query: str, cfg: Dict[str, Any], cache_dir: Path) -> Optional[PhotoResult]:
    """Fetch (or read from cache) a photo for `query`. Returns None on any failure."""
    slug = _slug(query)
    bin_path, meta_path = _cache_paths(cache_dir, slug)

    if bin_path.is_file() and meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            return PhotoResult(
                query=query,
                slug=slug,
                image_bytes=bin_path.read_bytes(),
                user=meta.get("user", "unknown"),
                page_url=meta.get("page_url", ""),
                image_url=meta.get("image_url", ""),
                cached=True,
            )
        except Exception as e:
            _LOG.warning("Cache corrupt for %s: %s", query, e)

    data = _pixabay_search(query, cfg)
    if not data:
        return None
    hit = _pick_hit(data, int(cfg["photos"]["min_width_px"]))
    if not hit:
        _LOG.warning("Pixabay zero results for %r", query)
        return None
    img_url = hit.get("largeImageURL") or hit.get("webformatURL")
    if not img_url:
        return None
    try:
        r = requests.get(img_url, timeout=float(cfg["photos"]["timeout_seconds"]))
        r.raise_for_status()
        image_bytes = r.content
    except requests.RequestException as e:
        _LOG.warning("Pixabay image download failed for %r: %s", query, e)
        return None

    cache_dir.mkdir(parents=True, exist_ok=True)
    bin_path.write_bytes(image_bytes)
    meta = {
        "query": query,
        "slug": slug,
        "user": hit.get("user", "unknown"),
        "page_url": hit.get("pageURL", ""),
        "image_url": img_url,
        "fetched_at": time.time(),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return PhotoResult(
        query=query, slug=slug, image_bytes=image_bytes,
        user=meta["user"], page_url=meta["page_url"], image_url=img_url,
        cached=False,
    )


def load_image_skia(data: bytes) -> Optional[skia.Image]:
    try:
        img = skia.Image.open(skia.Data.MakeWithCopy(data), encoded=True)
    except Exception as e:
        _LOG.warning("skia decode failed: %s", e)
        return None
    if img is None:
        return None
    return img


def _bilinear_paint() -> skia.Paint:
    p = skia.Paint(AntiAlias=True)
    try:
        p.setFilterQuality(skia.FilterQuality.kLow_FilterQuality)
    except Exception:
        pass
    return p


def center_crop_square(img: skia.Image) -> skia.Image:
    w, h = img.width(), img.height()
    side = min(w, h)
    x = (w - side) // 2
    y = (h - side) // 2
    surface = skia.Surface(side, side)
    c = surface.getCanvas()
    paint = _bilinear_paint()
    c.drawImage(img, skia.Rect.MakeXYWH(0, 0, side, side),
                skia.Rect.MakeXYWH(x, y, side, side), paint)
    return surface.makeImageSnapshot()


def draw_card(
    canvas: skia.Canvas,
    cfg: Dict[str, Any],
    img: Optional[skia.Image],
    cx: float,
    cy: float,
    size_px: float,
    outline_px: float,
    t: float,
    popin_t0: float,
    popin_duration: float = 0.35,
) -> None:
    """Draw a rounded-square framed photo card at (cx,cy), center-anchored."""
    if t < popin_t0:
        return
    elapsed = t - popin_t0
    if elapsed < popin_duration:
        u = elapsed / popin_duration
        c1 = 1.70158
        c3 = c1 + 1.0
        eased = 1.0 + c3 * (u - 1) ** 3 + c1 * (u - 1) ** 2
        scale = 0.6 + 0.4 * eased + 0.12 * (eased - 1.0)
    else:
        scale = 1.0
    import math as _m
    bob = 4.0 * (0.5 + 0.5 * _m.sin(2 * 3.14159 * 0.2 * t))

    canvas.save()
    canvas.translate(cx, cy + bob)
    canvas.scale(scale, scale)

    half = size_px / 2.0
    radius = size_px * float(cfg["photos"]["card_corner_radius_ratio"])
    rect = skia.Rect.MakeXYWH(-half, -half, size_px, size_px)
    rrect = skia.RRect.MakeRectXY(rect, radius, radius)

    canvas.save()
    clip = skia.Path()
    clip.addRRect(rrect)
    canvas.clipPath(clip, skia.ClipOp.kIntersect, True)
    if img is not None:
        sq = center_crop_square(img)
        paint = _bilinear_paint()
        canvas.drawImageRect(sq, skia.Rect.MakeWH(size_px, size_px), paint)
    else:
        black = skia.Paint(AntiAlias=True, Color=skia.Color(0, 0, 0))
        canvas.drawRRect(rrect, black)
    canvas.restore()

    white = cfg["colors"]["outline_white"]
    outline = skia.Paint(AntiAlias=True, Color=skia.Color(*white),
                         Style=skia.Paint.kStroke_Style, StrokeWidth=outline_px,
                         StrokeJoin=skia.Paint.kRound_Join,
                         StrokeCap=skia.Paint.kRound_Cap)
    canvas.drawRRect(rrect, outline)

    if img is None:
        from whatif.render import props as props_mod
        props_mod.draw_icon(canvas, cfg, "question_mark", 0.0, 0.0, size_px / 200.0, t)

    canvas.restore()