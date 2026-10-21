"""Remotion bridge for the production renderer.

The Python stages continue to own script, audio and photo preparation. This module
serializes those inputs into a renderer-neutral manifest and invokes the checked-in
Remotion composition.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from whatif import REPO_ROOT, get_logger
from whatif.render import photos as photos_mod

_LOG = get_logger("whatif.render.remotion")


def _data_url(data: bytes, query: str) -> str:
    mime = mimetypes.guess_type(query)[0] or "image/jpeg"
    if data.startswith(b"\x89PNG"):
        mime = "image/png"
    elif data.startswith(b"RIFF"):
        mime = "image/webp"
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _scene_starts(script: Dict[str, Any], voice: Dict[str, Any], duration: float) -> List[float]:
    words = [
        (str(item.get("word", "")).lower().strip(".,!?;:"), float(item.get("start", 0)))
        for item in voice.get("words", [])
    ]
    starts = [0.0]
    cursor = 0
    for scene in script["scenes"][1:]:
        first = str(scene.get("caption", "").split()[0] if scene.get("caption") else "")
        first = first.lower().strip(".,!?;:")
        found = None
        for index in range(cursor + 1, len(words)):
            if words[index][0] == first:
                found = words[index][1]
                cursor = index
                break
        fallback = duration * len(starts) / max(1, len(script["scenes"]))
        candidate = found if found is not None else fallback
        minimum = starts[-1] + min(0.25, duration / max(1, len(script["scenes"]) * 2))
        starts.append(min(duration, max(minimum, candidate)))
    return starts


def _collect_photos(
    script: Dict[str, Any], cfg: Dict[str, Any], run_dir: Path
) -> tuple[Dict[str, str], List[Dict[str, str]], List[str]]:
    cache_dir = REPO_ROOT / cfg["photos"]["cache_dir"]
    encoded: Dict[str, str] = {}
    credits: List[Dict[str, str]] = []
    fallbacks: List[str] = []
    for scene in script["scenes"]:
        for prop in scene.get("props") or []:
            if prop.get("type") != "photo":
                continue
            query = str(prop.get("query", ""))
            if query in encoded:
                continue
            result = photos_mod.fetch_photo(query, cfg, cache_dir)
            if result is None:
                fallbacks.append(query)
                credits.append({"query": query, "user": "", "page_url": "", "fallback": "question_mark"})
                continue
            encoded[query] = _data_url(result.image_bytes, query)
            credits.append({"query": query, "user": result.user, "page_url": result.page_url})
    (run_dir / "credits.json").write_text(json.dumps(credits, indent=2), encoding="utf-8")
    (run_dir / "render_warnings.json").write_text(
        json.dumps({"photo_fallbacks": fallbacks}, indent=2), encoding="utf-8"
    )
    return encoded, credits, fallbacks


def run(
    script: Dict[str, Any], run_dir: Path, cfg: Dict[str, Any]
) -> Dict[str, Any]:
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        raise RuntimeError(
            "npm is required for the Remotion renderer. Install Node.js 18+ and retry."
        )
    voice_path = run_dir / "voice.json"
    audio_path = run_dir / "audio_mix.wav"
    if not voice_path.is_file():
        raise RuntimeError("voice.json not found; run the voice stage first.")
    if not audio_path.is_file():
        raise RuntimeError("audio_mix.wav not found; run the music stage first.")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to mux audio into the Remotion video.")

    voice = json.loads(voice_path.read_text(encoding="utf-8"))
    target = float(cfg["video"]["target_seconds"])
    photos, _, fallbacks = _collect_photos(script, cfg, run_dir)
    scene_starts = _scene_starts(script, voice, target)
    _LOG.info("Scene starts: %s", ", ".join(f"{start:.2f}s" for start in scene_starts))
    music_meta_path = run_dir / "music.json"
    music_meta = json.loads(music_meta_path.read_text(encoding="utf-8")) if music_meta_path.is_file() else {}
    audit = {"missing": [scene["index"] for scene in script["scenes"] if not scene.get("caption")]}
    (run_dir / "captions_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")

    subject = script.get("opening_question", "WHAT IF").replace("What if ", "").replace(" vanished?", "")
    channel = str(cfg["channel_label_template"]).format(subject=subject).upper()
    colors = cfg.get("colors", {})
    public_audio_dir = REPO_ROOT / "public" / "whatif-audio"
    public_audio_dir.mkdir(parents=True, exist_ok=True)
    public_audio_name = f"{run_dir.name}.wav"
    public_audio_path = public_audio_dir / public_audio_name
    shutil.copyfile(audio_path, public_audio_path)

    manifest = {
        "script": script,
        "words": voice.get("words", []),
        "audioPath": f"/whatif-audio/{public_audio_name}",
        "width": int(cfg["video"]["width"]),
        "height": int(cfg["video"]["height"]),
        "fps": int(cfg["video"]["fps"]),
        "durationSeconds": target,
        "channelLabel": channel,
        "beats": [float(beat) for beat in music_meta.get("beats", [])],
        "colors": {
            "background": "#000000",
            "outline": "#ffffff",
            "active": _rgb_hex(colors.get("caption_active", [255, 215, 0])),
            "emphasis": _rgb_hex(colors.get("caption_secondary", [255, 140, 0])),
            "text": _rgb_hex(colors.get("caption_white", [255, 255, 255])),
        },
        "photos": photos,
        "sceneStarts": scene_starts,
    }
    manifest_path = run_dir / "remotion_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    output = run_dir / "final.mp4"
    command = [
        npm, "run", "render", "--",
        str(output),
        f"--props={manifest_path.resolve()}",
    ]
    _LOG.info("Starting Remotion render: %d frames at %dx%d", round(target * manifest["fps"]),
              manifest["width"], manifest["height"])
    try:
        proc = subprocess.run(command, cwd=str(REPO_ROOT), capture_output=True, text=True)
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(f"Remotion render failed ({proc.returncode}): {detail[-1200:]}")
        if not output.is_file():
            raise RuntimeError(f"Remotion completed without creating {output}")
        _mux_audio(ffmpeg, output, audio_path)
    finally:
        if public_audio_path.is_file():
            public_audio_path.unlink()
    _LOG.info("Remotion render complete: %s", output)
    return {
        "video_path": str(output),
        "duration_seconds": target,
        "frames": round(target * manifest["fps"]),
        "photo_fallbacks": fallbacks,
        "renderer": "remotion",
    }


def _rgb_hex(value: Any) -> str:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return "#FFFFFF"
    return "#{:02X}{:02X}{:02X}".format(int(value[0]), int(value[1]), int(value[2]))


def _mux_audio(ffmpeg: str, video_path: Path, audio_path: Path) -> None:
    """Replace the rendered container with a video-plus-audio MP4."""
    muxed = video_path.with_suffix(".muxed.mp4")
    command = [
        ffmpeg, "-y", "-loglevel", "error",
        "-i", str(video_path), "-i", str(audio_path),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart", str(muxed),
    ]
    proc = subprocess.run(command, capture_output=True, text=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"ffmpeg audio mux failed ({proc.returncode}): {detail[-1000:]}")
    muxed.replace(video_path)
