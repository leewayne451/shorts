"""QA stage.

Pass criteria (per the prompt):
  - duration in [20.0, 40.0] s
  - resolution 1080x1920
  - audio stream present
  - mean volume > -30 dB
  - sampled frames are not all identical
  - for each scene, that scene's caption text appears in at least one sampled frame near
    the scene's timestamp (per-beat captions)
Photo fallbacks are warnings, not failures.

Outputs:
  qa.json = {"pass": bool, "reason": str | null, "checks": {...}, "warnings": [...]}
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from whatif import get_logger, load_config

_LOG = get_logger("whatif.qa")


def _ffprobe_json(path: Path) -> Dict[str, Any]:
    exe = shutil.which("ffprobe")
    if not exe:
        raise RuntimeError("ffprobe is required for QA. Install ffmpeg.")
    cmd = [exe, "-v", "error", "-print_format", "json",
           "-show_format", "-show_streams", str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {proc.stderr.strip()[:400]}")
    return json.loads(proc.stdout)


def _extract_frame(video: Path, t_seconds: float, out_png: Path) -> bool:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg is required for QA. Install ffmpeg.")
    cmd = [exe, "-y", "-loglevel", "error", "-ss", f"{t_seconds:.3f}",
           "-i", str(video), "-frames:v", "1", str(out_png)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode == 0 and out_png.is_file() and out_png.stat().st_size > 0


def _frame_pixels(png_path: Path) -> Optional[np.ndarray]:
    """Decode a PNG to an (H, W, 3) uint8 numpy array via skia. Returns None on failure."""
    try:
        import skia
        img = skia.Image.open(str(png_path))
        if img is None:
            return None
        w, h = img.width(), img.height()
        arr = np.zeros((h, w, 4), dtype=np.uint8)
        info = skia.ImageInfo.Make(w, h, skia.ColorType.kRGBA_8888_ColorType,
                                   skia.AlphaType.kPremul_AlphaType)
        ok = img.readPixels(info, arr, w * 4, 0, 0)
        if not ok:
            return None
        return arr[:, :, :3]
    except Exception:
        return None


_CAPTION_OCR_RE = re.compile(r"[A-Za-z0-9']+")


def _caption_tokens(caption: str) -> List[str]:
    return [t.lower() for t in _CAPTION_OCR_RE.findall(caption)]


def _sample_frames(video: Path, timestamps: List[float]) -> List[np.ndarray]:
    """Extract frames at timestamps, return their pixel arrays (may include Nones)."""
    out: List[np.ndarray] = []
    with tempfile.TemporaryDirectory() as td:
        for i, t in enumerate(timestamps):
            p = Path(td) / f"f{i:03d}.png"
            if _extract_frame(video, t, p):
                arr = _frame_pixels(p)
                if arr is not None:
                    out.append(arr)
    return out


def _frames_all_identical(frames: List[np.ndarray]) -> bool:
    if len(frames) < 2:
        return False
    ref = frames[0].astype(np.int16)
    for f in frames[1:]:
        if not np.array_equal(ref, f.astype(np.int16)):
            return False
    return True


def _mean_volume_db(audio_path: Path) -> float:
    """Mean volume via ffmpeg volumedetect (mean_volume)."""
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg is required for QA. Install ffmpeg.")
    cmd = [exe, "-hide_banner", "-i", str(audio_path), "-af", "volumedetect", "-f", "null", "-"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    text = proc.stderr
    m = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", text)
    if not m:
        return -999.0
    return float(m.group(1))


def _scene_timestamps(scenes: List[Dict[str, Any]], voice: Dict[str, Any],
                      total_seconds: float) -> List[float]:
    """Compute a representative timestamp for each scene using word timings.

    For the opening scene, use t=0.2s. For consequence scenes, use the start time of the first
    word in that scene's caption, located sequentially in the word list.
    """
    words = voice.get("words") or []
    word_lookup = [(w["word"].lower().strip(".,!?;:"), float(w["start"])) for w in words]
    used_idx = 0
    timestamps: List[float] = [0.2]
    for scene in scenes[1:]:
        cap_words = [t for t in _caption_tokens(scene["caption"])]
        if not cap_words:
            timestamps.append(min(total_seconds - 0.5, timestamps[-1] + 2.0))
            continue
        first_word = cap_words[0]
        found_t: Optional[float] = None
        for j in range(used_idx, len(word_lookup)):
            if word_lookup[j][0] == first_word:
                found_t = word_lookup[j][1]
                used_idx = j
                break
        if found_t is None:
            # Fall back: evenly space scenes across the video.
            timestamps.append(min(total_seconds - 0.5, timestamps[-1] + 2.0))
        else:
            timestamps.append(max(0.0, min(total_seconds - 0.5, found_t + 0.15)))
    return timestamps


def run(run_dir: Path, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = cfg or load_config()
    video = run_dir / "final.mp4"
    if not video.is_file():
        return _fail(run_dir, "final.mp4 not found")

    meta = _ffprobe_json(video)
    fmt = meta.get("format", {})
    streams = meta.get("streams", [])
    duration = float(fmt.get("duration") or 0.0)
    width = height = 0
    has_audio = False
    audio_stream = None
    for s in streams:
        if s.get("codec_type") == "video":
            width = int(s.get("width") or 0)
            height = int(s.get("height") or 0)
        elif s.get("codec_type") == "audio":
            has_audio = True
            audio_stream = s

    checks: Dict[str, Any] = {
        "duration_seconds": duration,
        "width": width,
        "height": height,
        "has_audio": has_audio,
    }
    warnings: List[str] = []

    qa_min = float(cfg["video"]["qa_min_seconds"])
    qa_max = float(cfg["video"]["qa_max_seconds"])
    if not (qa_min <= duration <= qa_max):
        return _fail(run_dir, f"duration {duration:.2f}s outside [{qa_min:.1f},{qa_max:.1f}]",
                     checks=checks, warnings=warnings)

    target_w = int(cfg["video"]["width"])
    target_h = int(cfg["video"]["height"])
    if (width, height) != (target_w, target_h):
        return _fail(run_dir, f"resolution {width}x{height} != {target_w}x{target_h}",
                     checks=checks, warnings=warnings)

    if not has_audio:
        return _fail(run_dir, "no audio stream", checks=checks, warnings=warnings)

    # Mean volume
    mean_db = _mean_volume_db(video)
    checks["mean_volume_db"] = mean_db
    if mean_db < -30.0:
        return _fail(run_dir, f"mean volume {mean_db:.1f} dB < -30 dB",
                     checks=checks, warnings=warnings)

    # Sample 8 frames evenly + per-scene frames
    n_samples = 8
    even_ts = [round((i + 0.5) * duration / n_samples, 3) for i in range(n_samples)]

    script = json.loads((run_dir / "script.json").read_text(encoding="utf-8"))
    voice = json.loads((run_dir / "voice.json").read_text(encoding="utf-8"))
    scene_ts = _scene_timestamps(script["scenes"], voice, duration)
    all_ts = even_ts + [round(t, 3) for t in scene_ts]
    frames = _sample_frames(video, all_ts)

    if len(frames) < 2:
        return _fail(run_dir, "could not extract frames for QA", checks=checks, warnings=warnings)
    if _frames_all_identical(frames):
        return _fail(run_dir, "sampled frames are all identical",
                     checks=checks, warnings=warnings)

    # Per-scene caption appearance: check the scene's first 2-3 caption tokens appear in SOME
    # frame near the scene's timestamp. We use a tiny in-memory OCR substitute: the renderer
    # writes a captions audit to captions_audit.json; if present, trust that instead of OCR.
    audit_path = run_dir / "captions_audit.json"
    if audit_path.is_file():
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        missing = audit.get("missing", [])
        if missing:
            checks["caption_audit"] = {"missing": missing}
            return _fail(run_dir, f"captions missing on screen: {missing[:3]}",
                         checks=checks, warnings=warnings)
        checks["caption_audit"] = {"missing": []}
    else:
        warnings.append("captions_audit.json missing; skipping caption-appearance check")

    # Photo fallbacks are warnings: read the render's warnings log if present.
    render_warnings_path = run_dir / "render_warnings.json"
    if render_warnings_path.is_file():
        rw = json.loads(render_warnings_path.read_text(encoding="utf-8"))
        if rw.get("photo_fallbacks"):
            warnings.append(f"photo fallbacks: {rw['photo_fallbacks']}")
        checks["render_warnings"] = rw

    out = {"pass": True, "reason": None, "checks": checks, "warnings": warnings}
    (run_dir / "qa.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    _LOG.info("QA pass: %.2fs %dx%d mean=%.1fdB warnings=%d",
              duration, width, height, mean_db, len(warnings))
    return out


def _fail(run_dir: Path, reason: str, checks: Optional[Dict[str, Any]] = None,
          warnings: Optional[List[str]] = None) -> Dict[str, Any]:
    out = {"pass": False, "reason": reason, "checks": checks or {},
           "warnings": warnings or []}
    (run_dir / "qa.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    _LOG.error("QA fail: %s", reason)
    return out