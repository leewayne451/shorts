"""Voice stage: synthesize narration with edge-tts (primary) or espeak-ng (fallback).

Inputs:
  script.json   (from script_stage)
Outputs:
  voice.wav        — normalized mono 48 kHz PCM
  voice.json       — {"duration_seconds", "words":[{"word","start","end"}], "engine",
                      "rate", "text", "shorten_attempts"}

The text spoken is the opening question followed by each consequence caption, in scene order,
concatenated with a short pause between them. Captions are per-beat in this format, so we still
emit word timings (used by the fact-check word audit and by the renderer to place beats).

Shorten-and-retry:
  If synthesized duration > cfg["voice"]["max_seconds_before_rate_bump"], first bump rate up to
  cfg["voice"]["max_rate_bump"] and re-synthesize once. If still > limit, ask the LLM to shorten
  captions and re-synthesize (up to cfg["voice"]["max_shorten_attempts"]). Fail with a clear
  error after that.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

from whatif import get_logger, load_config
from whatif.llm import GroqError, chat_json

_LOG = get_logger("whatif.voice")

_SAMPLE_RATE = 48000
_CHANNELS = 1
_SAMPLE_WIDTH = 2  # int16


# ---------------------------------------------------------------------------
# Narration text assembly
# ---------------------------------------------------------------------------
def _narration_text(script: Dict[str, Any]) -> str:
    """Opening question + consequence captions, joined by a single space (or newline)."""
    parts: List[str] = [script["opening_question"].strip()]
    for scene in script["scenes"][1:]:
        cap = scene["caption"].strip()
        if cap:
            parts.append(cap)
    return " ".join(parts)


# ---------------------------------------------------------------------------
# edge-tts synthesis
# ---------------------------------------------------------------------------
async def _edge_synth(text: str, voice: str, rate: str, out_mp3: Path) -> List[Dict[str, Any]]:
    """Synthesize with edge-tts, capturing WordBoundary events.

    Returns a list of {"word", "start", "end"} in seconds. If only sentence boundaries are
    delivered (some edge-tts versions default to that), we return sentence-level entries; the
    caller then proportionally expands them.
    """
    import edge_tts  # local import; the dependency is required for primary path

    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)

    events: List[Dict[str, Any]] = []
    # edge-tts 7.x: stream() yields dicts with "type": "audio" | "WordBoundary" | "SentenceBoundary".
    with out_mp3.open("wb") as f:
        async for chunk in communicate.stream():
            t = chunk.get("type")
            if t == "audio":
                f.write(chunk["data"])
            elif t in ("WordBoundary", "SentenceBoundary"):
                # edge-tts time units are 100ns ("offset", "duration" in 10_000,000 per second)
                start_s = chunk.get("offset", 0) / 10_000_000.0
                dur_s = chunk.get("duration", 0) / 10_000_000.0
                events.append({
                    "word": chunk.get("text", ""),
                    "start": start_s,
                    "end": start_s + dur_s,
                    "kind": t,
                })
    return events


def _expand_sentence_boundaries(text: str, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """If only sentence boundaries came back, split each sentence into words and interpolate
    timings proportional to character count within that sentence window."""
    if not events:
        return []
    if all(e.get("kind") == "WordBoundary" for e in events):
        return [{"word": e["word"], "start": e["start"], "end": e["end"]} for e in events]

    out: List[Dict[str, Any]] = []
    for e in events:
        sent = (e.get("word") or "").strip()
        if not sent:
            continue
        t0, t1 = e["start"], e["end"]
        span = max(1e-6, t1 - t0)
        words = sent.split()
        if not words:
            continue
        total_chars = sum(len(w) for w in words) or 1
        cursor = t0
        for w in words:
            frac = len(w) / total_chars
            dur = span * frac
            out.append({"word": w, "start": cursor, "end": cursor + dur})
            cursor += dur
    return out


# ---------------------------------------------------------------------------
# espeak-ng fallback
# ---------------------------------------------------------------------------
def _espeak_synth(text: str, espeak_voice: str, out_wav: Path) -> float:
    """Synthesize with espeak-ng. Returns estimated duration in seconds."""
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        raise RuntimeError(
            "espeak-ng is not installed and edge-tts failed. Install espeak-ng "
            "(apt-get install espeak-ng, brew install espeak-ng, or on Windows download from "
            "https://github.com/espeak-ng/espeak-ng/releases) and retry."
        )
    # -v selects the voice; -s 165 words-per-minute reads at ~ the normal default.
    cmd = [exe, "-v", espeak_voice, "-s", "165", "-w", str(out_wav), text]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"espeak-ng failed ({proc.returncode}): {proc.stderr.strip()[:400]}")
    with wave.open(str(out_wav), "rb") as w:
        frames = w.getnframes()
        rate = w.getframerate() or 22050
    return frames / float(rate)


def _estimate_espeak_words(text: str, total_seconds: float) -> List[Dict[str, Any]]:
    """Character-proportional per-word timings scaled to measured duration."""
    words = [w for w in re.split(r"\s+", text.strip()) if w]
    if not words:
        return []
    total_chars = sum(len(w) for w in words) or 1
    t = 0.0
    out: List[Dict[str, Any]] = []
    for w in words:
        frac = len(w) / total_chars
        dur = total_seconds * frac
        out.append({"word": w, "start": t, "end": t + dur})
        t += dur
    return out


# ---------------------------------------------------------------------------
# Loudness normalization + silence trim (ffmpeg)
# ---------------------------------------------------------------------------
def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _normalize_and_trim(src: Path, dst: Path, cfg: Dict[str, Any]) -> None:
    """Trim silence at both ends, normalize loudness with loudnorm, output 48 kHz mono PCM."""
    if not _ffmpeg_available():
        raise RuntimeError(
            "ffmpeg is required to normalize the voice track. Install ffmpeg and retry."
        )
    lufs = cfg["voice"]["loudnorm_target_lufs"]
    thresh = cfg["voice"]["trim_silence_threshold_db"]
    # Two-pass loudnorm would be ideal, but a single-pass is sufficient for shorts.
    af = (
        f"silenceremove=start_periods=1:start_silence=0.05:start_threshold={thresh}dB:"
        f"stop_periods=1:stop_silence=0.05:stop_threshold={thresh}dB,"
        f"loudnorm=I={lufs}:TP=-1.5:LRA=11,"
        f"aresample={_SAMPLE_RATE}"
    )
    cmd = [
        "ffmpeg", "-y", "-i", str(src), "-af", af,
        "-ac", str(_CHANNELS), "-ar", str(_SAMPLE_RATE),
        "-c:a", "pcm_s16le", str(dst),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg normalize failed: {proc.stderr.strip()[:600]}")


# ---------------------------------------------------------------------------
# LLM shorten
# ---------------------------------------------------------------------------
_SHORTEN_SYSTEM = """You are an editor shortening scene captions for a ~30-second vertical
short. You will be given a JSON array of caption strings. Return a JSON object of the form
{"captions": ["<shortened>", ...]} with the SAME number of items, in the SAME order, each
shortened to be at most 60% of its original word count, preserving the meaning. Do not add
or remove items. Return only the JSON object."""


def _shorten_captions(cfg: Dict[str, Any], captions: List[str]) -> List[str]:
    user = json.dumps({"captions": captions}, ensure_ascii=False)
    try:
        data = chat_json(
            cfg, system=_SHORTEN_SYSTEM, user=user,
            temperature=0.3, max_tokens=1024,
        )
    except GroqError as e:
        raise RuntimeError(f"LLM shorten failed: {e}") from e
    out = data.get("captions")
    if not isinstance(out, list) or len(out) != len(captions):
        raise RuntimeError("LLM shorten returned wrong shape")
    return [str(x).strip() for x in out]


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
def run(
    script: Dict[str, Any],
    run_dir: Path,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cfg = cfg or load_config()
    voice_name = cfg["voice"]["voice"]
    espeak_voice = cfg["voice"]["espeak_voice"]
    max_seconds = float(cfg["voice"]["max_seconds_before_rate_bump"])
    max_rate = cfg["voice"]["max_rate_bump"]
    max_shorten = int(cfg["voice"]["max_shorten_attempts"])

    text = _narration_text(script)
    _LOG.info("Narration text (%d chars): %r", len(text), text[:160] + ("…" if len(text) > 160 else ""))

    raw_mp3 = run_dir / "voice_raw.mp3"
    raw_wav = run_dir / "voice_raw.wav"
    final_wav = run_dir / "voice.wav"

    engine = "edge-tts"
    rate = "+0%"
    words: List[Dict[str, Any]] = []
    duration = 0.0
    shorten_attempts = 0

    def try_edge(text_in: str, rate_in: str) -> Optional[float]:
        """Returns duration in seconds, or None if edge-tts failed."""
        try:
            events = asyncio.run(_edge_synth(text_in, voice_name, rate_in, raw_mp3))
        except Exception as e:
            _LOG.warning("edge-tts failed: %s", e)
            return None
        if not raw_mp3.is_file() or raw_mp3.stat().st_size == 0:
            _LOG.warning("edge-tts produced no audio")
            return None
        _normalize_and_trim(raw_mp3, final_wav, cfg)
        with wave.open(str(final_wav), "rb") as w:
            dur = w.getnframes() / float(w.getframerate())
        nonlocal_words = _expand_sentence_boundaries(text_in, events)
        words.clear()
        words.extend(nonlocal_words)
        return dur

    def try_espeak(text_in: str) -> Optional[float]:
        try:
            dur = _espeak_synth(text_in, espeak_voice, raw_wav)
        except Exception as e:
            _LOG.warning("espeak-ng failed: %s", e)
            return None
        _normalize_and_trim(raw_wav, final_wav, cfg)
        with wave.open(str(final_wav), "rb") as w:
            real_dur = w.getnframes() / float(w.getframerate())
        words.clear()
        words.extend(_estimate_espeak_words(text_in, real_dur))
        return real_dur

    # 1) try edge-tts at normal rate
    duration = try_edge(text, rate) or 0.0
    if duration == 0.0:
        engine = "espeak-ng"
        duration = try_espeak(text) or 0.0
        if duration == 0.0:
            raise RuntimeError(
                "Both edge-tts and espeak-ng failed to synthesize audio. "
                "Check network access (edge-tts) and that espeak-ng is installed."
            )

    # 2) if too long, bump rate up to the max
    if duration > max_seconds and engine == "edge-tts":
        _LOG.info("Voice %.2fs > %.2fs; retrying at rate %s", duration, max_seconds, max_rate)
        bumped = try_edge(text, max_rate)
        if bumped:
            duration = bumped
            rate = max_rate

    # 3) if still too long, ask the LLM to shorten captions and retry
    while duration > max_seconds and shorten_attempts < max_shorten:
        shorten_attempts += 1
        _LOG.info("Voice %.2fs still too long; shortening captions (attempt %d/%d)",
                  duration, shorten_attempts, max_shorten)
        captions = [s["caption"] for s in script["scenes"][1:]]
        if not captions:
            break
        try:
            shortened = _shorten_captions(cfg, captions)
        except RuntimeError as e:
            _LOG.warning("Shorten failed: %s", e)
            break
        # Write back to script so the renderer uses the shortened captions too.
        for scene, new_cap in zip(script["scenes"][1:], shortened):
            scene["caption"] = new_cap
        (run_dir / "script.json").write_text(
            json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        text = _narration_text(script)
        if engine == "edge-tts":
            new_dur = try_edge(text, rate)
        else:
            new_dur = try_espeak(text)
        if not new_dur:
            break
        duration = new_dur

    if duration > max_seconds:
        _LOG.warning(
            "Voice is %.2fs (> %.2fs) after %d shorten attempts; continuing (QA will judge).",
            duration, max_seconds, shorten_attempts,
        )

    out = {
        "duration_seconds": duration,
        "words": words,
        "engine": engine,
        "rate": rate,
        "text": text,
        "shorten_attempts": shorten_attempts,
    }
    (run_dir / "voice.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _LOG.info("Voice done: engine=%s rate=%s duration=%.2fs words=%d",
              engine, rate, duration, len(words))
    return out


def load(run_dir: Path) -> Dict[str, Any]:
    return json.loads((run_dir / "voice.json").read_text(encoding="utf-8"))