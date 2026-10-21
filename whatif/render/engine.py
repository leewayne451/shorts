"""Render engine: draw frames with skia, pipe to ffmpeg, mux audio_mix.wav, write final.mp4.

Public API:
  run(script, run_dir, cfg) -> dict
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import skia

from whatif import REPO_ROOT, get_logger, load_config
from whatif.render import characters as char_mod
from whatif.render import photos as photos_mod
from whatif.render import scenes as scenes_mod
from whatif.render import captions as captions_mod

_LOG = get_logger("whatif.render.engine")

_FONT_TOP_LABEL_SIZE = 40


def _top_label_text(cfg: Dict[str, Any], subject: str) -> str:
    return str(cfg["channel_label_template"]).format(subject=subject).upper()


def _draw_top_label(canvas, cfg, text):
    from whatif import REPO_ROOT
    tf = skia.Typeface.MakeFromFile(str(REPO_ROOT / cfg["captions"]["font_primary"])) \
        or skia.Typeface.MakeFromName(cfg["captions"]["font_fallback"], skia.FontStyle.Bold()) \
        or skia.Typeface.MakeDefault()
    font = skia.Font(tf, _FONT_TOP_LABEL_SIZE)
    tw = font.measureText(text)
    cx = cfg["video"]["width"] / 2.0
    y = cfg["video"]["safe_top_px"] + _FONT_TOP_LABEL_SIZE
    p = skia.Paint(AntiAlias=True, Color=skia.Color(255, 255, 255))
    canvas.drawString(text, cx - tw / 2.0, y, font, p)


def _scene_timings(script: Dict[str, Any], voice: Dict[str, Any],
                   target_seconds: float) -> List[Dict[str, Any]]:
    """Return per-scene [start,end] in seconds, derived from word timings."""
    words = voice.get("words") or []
    scenes = script["scenes"]
    if not words:
        # Fallback: even spacing.
        n = len(scenes)
        return [{"index": i, "start": target_seconds * i / n,
                 "end": target_seconds * (i + 1) / n} for i in range(n)]

    # Map scene i to start time of its first caption word (scene 0 = t=0).
    tokens = [(w["word"].lower().strip(".,!?;:"), float(w["start"])) for w in words]
    out: List[Dict[str, Any]] = []
    cursor = 0
    starts: List[float] = [0.0]
    for scene in scenes[1:]:
        cap_words = [t.lower() for t in scene["caption"].split() if t.strip()]
        first = cap_words[0] if cap_words else ""
        start = None
        for j in range(cursor, len(tokens)):
            if tokens[j][0] == first:
                start = tokens[j][1]
                cursor = j
                break
        starts.append(start if start is not None else starts[-1] + 2.0)

    for i, s in enumerate(scenes):
        start = starts[i]
        end = starts[i + 1] if i + 1 < len(scenes) else target_seconds
        out.append({"index": s["index"], "start": start, "end": end})
    return out


def _apply_shake(canvas, cfg, scene, t, scene_start) -> None:
    if not scene.get("shake"):
        return
    skcfg = cfg["shake"]
    dur = skcfg["duration_ms"] / 1000.0
    elapsed = t - scene_start
    if elapsed > dur:
        return
    u = max(0.0, min(1.0, elapsed / dur))
    amp = float(skcfg["amplitude_px"]) * (1.0 - u)
    # Deterministic pseudo-shake using scene index + time.
    ang = (scene["index"] * 1.7 + t * 12.0)
    canvas.translate(math.sin(ang) * amp, math.cos(ang * 1.3) * amp)


def _load_photos(script, cfg) -> tuple[Dict[str, Optional[skia.Image]], List[Dict[str, str]]]:
    cache_dir = REPO_ROOT / cfg["photos"]["cache_dir"]
    images: Dict[str, Optional[skia.Image]] = {}
    credits: List[Dict[str, str]] = []
    for scene in script["scenes"]:
        for prop in scene.get("props") or []:
            if prop.get("type") != "photo":
                continue
            q = prop["query"]
            if q in images:
                continue
            res = photos_mod.fetch_photo(q, cfg, cache_dir)
            if res is None:
                images[q] = None
                credits.append({"query": q, "user": "", "page_url": "", "fallback": "question_mark"})
                continue
            images[q] = photos_mod.load_image_skia(res.image_bytes)
            credits.append({"query": q, "user": res.user, "page_url": res.page_url})
    return images, credits


def run(script: Dict[str, Any], run_dir: Path, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Render with Remotion.

    The legacy Skia helpers remain available for unit tests and compatibility, but
    production rendering is delegated to the React composition.
    """
    cfg = cfg or load_config()
    from whatif.render import remotion
    return remotion.run(script, run_dir, cfg)


def run_skia(script: Dict[str, Any], run_dir: Path, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Legacy Skia renderer retained as an explicit compatibility fallback."""
    cfg = cfg or load_config()
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found. Install ffmpeg and retry.")

    target = float(cfg["video"]["target_seconds"])
    w = int(cfg["video"]["width"])
    h = int(cfg["video"]["height"])
    fps = int(cfg["video"]["fps"])
    total_frames = int(round(target * fps))

    voice = json.loads((run_dir / "voice.json").read_text(encoding="utf-8"))
    audio_mix = run_dir / "audio_mix.wav"
    if not audio_mix.is_file():
        raise RuntimeError("audio_mix.wav not found; run the music stage first.")

    photos, credits = _load_photos(script, cfg)
    (run_dir / "credits.json").write_text(json.dumps(credits, indent=2, ensure_ascii=False),
                                          encoding="utf-8")
    fallbacks = [c["query"] for c in credits if c.get("fallback")]
    (run_dir / "render_warnings.json").write_text(
        json.dumps({"photo_fallbacks": fallbacks}, indent=2), encoding="utf-8"
    )

    scene_times = _scene_timings(script, voice, target)

    # Caption audit: for each scene, mark whether its caption will be rendered on screen.
    audit = {"missing": []}
    for s in script["scenes"]:
        if not s.get("caption"):
            audit["missing"].append(s["index"])
    (run_dir / "captions_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")

    cast_by_id = {c["id"]: c for c in script["cast"]}
    subject_label = _top_label_text(cfg, _extract_subject(script["opening_question"]))

    out_mp4 = run_dir / "final.mp4"
    cmd = [
        ffmpeg, "-y",
        "-f", "rawvideo", "-pix_fmt", "bgra",
        "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
        "-i", str(audio_mix),
        "-c:v", "libx264", "-preset", "medium", "-crf", str(int(cfg["video"]["crf"])),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", str(cfg["video"]["audio_bitrate"]),
        "-shortest", "-movflags", "+faststart",
        str(out_mp4),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)

    surface = skia.Surface(w, h)
    try:
        for i in range(total_frames):
            t = i / fps
            canvas = surface.getCanvas()
            canvas.clear(skia.Color(*cfg["colors"]["background"]))

            _draw_top_label(canvas, cfg, subject_label)

            # Find active scene
            active = scene_times[0]
            for st in scene_times:
                if st["start"] <= t < st["end"]:
                    active = st
                    break
            scene = script["scenes"][active["index"]]

            # Shake wraps scene drawing
            canvas.save()
            _apply_shake(canvas, cfg, scene, t, active["start"])
            scenes_mod.render_scene(canvas, cfg, script, scene, cast_by_id, t,
                                    active["start"], {"photos": photos})
            canvas.restore()

            # Caption line for this scene (per-beat)
            placements = captions_mod.layout_line(scene["caption"],
                                                  scene.get("emphasis") or [], cfg)
            cap_cy = h - cfg["video"]["safe_bottom_px"] - 120
            captions_mod.draw_caption_line(canvas, cfg, placements,
                                           w / 2.0, cap_cy, active["start"] + 0.05, t)

            arr = surface.makeImageSnapshot().toarray()
            # skia surface toarray is RGBA; convert to BGRA
            bgra = bytearray(arr.shape[0] * arr.shape[1] * 4)
            bgra[0::4] = arr[:, :, 2].tobytes()
            bgra[1::4] = arr[:, :, 1].tobytes()
            bgra[2::4] = arr[:, :, 0].tobytes()
            bgra[3::4] = arr[:, :, 3].tobytes()
            proc.stdin.write(bytes(bgra))
    finally:
        proc.stdin.close()
        stderr = proc.stderr.read().decode(errors="ignore") if proc.stderr else ""
        proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg render failed ({proc.returncode}): {stderr[:600]}")

    _LOG.info("Render done: %s (%.1fs, %d frames)", out_mp4, target, total_frames)
    return {"video_path": str(out_mp4), "duration_seconds": target,
            "frames": total_frames, "photo_fallbacks": fallbacks}


def _extract_subject(opening_question: str) -> str:
    import re
    m = re.match(r"^\s*what\s+if\s+(.+?)\s+vanished\?\s*$", opening_question, re.I)
    return m.group(1) if m else opening_question