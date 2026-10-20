"""Music stage: procedural mysterious bed, ~30 s, ducked under the voice.

Outputs:
  music.wav     — 48 kHz mono float32-encoded-as-pcm16, exact target_seconds length
  music.json    — {"bpm","duration_seconds","beats":[t,...],"ducking_gain_db","mood"}
  audio_mix.wav — voice + ducked music, target length (used by the renderer)
"""
from __future__ import annotations

import json
import math
import subprocess
import shutil
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from whatif import get_logger, load_config

_LOG = get_logger("whatif.music")
_SR = 48000


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg is required for music muxing. Install ffmpeg.")
    return exe


def _read_wav_mono(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        n = w.getnframes()
        rate = w.getframerate()
        sw = w.getsampwidth()
        data = w.readframes(n)
    if sw != 2:
        raise RuntimeError(f"Expected 16-bit WAV at {path}, got sampwidth={sw}")
    arr = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    if rate != _SR:
        # Linear resample (fine for the short music bed; voice is already 48k).
        new_n = int(round(len(arr) * _SR / rate))
        xp = np.linspace(0.0, 1.0, num=len(arr), endpoint=False)
        x = np.linspace(0.0, 1.0, num=new_n, endpoint=False)
        arr = np.interp(x, xp, arr).astype(np.float32)
    return arr


def _write_wav_mono(path: Path, x: np.ndarray) -> None:
    x = np.clip(x, -1.0, 1.0)
    pcm = (x * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_SR)
        w.writeframes(pcm.tobytes())


def _sine(freq: float, seconds: float, phase: float = 0.0) -> np.ndarray:
    t = np.arange(int(seconds * _SR), dtype=np.float32) / _SR
    return np.sin(2 * math.pi * freq * t + phase).astype(np.float32)


def _detuned_pad(freq: float, seconds: float, detune_cents: float) -> np.ndarray:
    a = 2 ** (-detune_cents / 1200.0)
    b = 2 ** (+detune_cents / 1200.0)
    saw_a = _sine(freq * a, seconds)
    saw_b = _sine(freq * b, seconds)
    # Cheap lowpass via exponential moving average.
    y = np.empty_like(saw_a)
    alpha = 0.05
    prev = 0.0
    for i in range(len(saw_a)):
        prev = prev + alpha * (saw_a[i] - prev)
        y[i] = prev
    return 0.5 * (y + saw_b)


def _one_pole_lowpass(x: np.ndarray, cutoff_hz: float) -> np.ndarray:
    alpha = 1.0 - math.exp(-2 * math.pi * cutoff_hz / _SR)
    y = np.empty_like(x)
    prev = 0.0
    for i in range(len(x)):
        prev = prev + alpha * (x[i] - prev)
        y[i] = prev
    return y


def _envelope(n: int, attack_s: float, release_s: float) -> np.ndarray:
    a = int(attack_s * _SR)
    r = int(release_s * _SR)
    env = np.ones(n, dtype=np.float32)
    if a > 0:
        env[:a] = np.linspace(0, 1, a, dtype=np.float32)
    if r > 0:
        env[-r:] = np.linspace(1, 0, r, dtype=np.float32)
    return env


def _render_bed(cfg: Dict[str, Any], seconds: float, seed: int = 0) -> tuple[np.ndarray, List[float], int]:
    mcfg = cfg["music"]
    bpm_lo, bpm_hi = mcfg["bpm_range"]
    rng = np.random.default_rng(seed)
    bpm = int(rng.integers(bpm_lo, bpm_hi + 1))
    beat_s = 60.0 / bpm
    bar_s = 4 * beat_s
    n = int(seconds * _SR)
    out = np.zeros(n, dtype=np.float32)

    # Sub bass: slow single sine at the root.
    root = float(mcfg["root_note_hz"])
    sub = _sine(root, seconds) * (10 ** (mcfg["sub_gain_db"] / 20.0))
    sub *= _envelope(n, 0.5, 0.5)
    out += sub[:n]

    # Pad: root, minor third, perfect fifth, held over each bar, sparsely retriggered.
    scale = mcfg["minor_scale_offsets"]
    notes = [root * 2 ** (scale[0] / 12.0),
             root * 2 ** (scale[2] / 12.0),
             root * 2 ** (scale[4] / 12.0)]
    pad_gain = 10 ** (mcfg["pad_gain_db"] / 20.0)
    pad = np.zeros(n, dtype=np.float32)
    for ni, f in enumerate(notes):
        layer = _detuned_pad(f, seconds, mcfg["pad_detune_cents"])
        # Sparse amplitude LFO so the pad breathes, not drones.
        t = np.arange(n, dtype=np.float32) / _SR
        lfo = 0.6 + 0.4 * np.sin(2 * math.pi * (0.07 + 0.02 * ni) * t + ni)
        pad += layer[:n] * lfo
    pad = _one_pole_lowpass(pad, float(mcfg["pad_lowpass_hz"]))
    out += pad * pad_gain * _envelope(n, 1.0, 1.5)

    # Soft low tom on each bar start.
    tom_gain = 10 ** (mcfg["tom_gain_db"] / 20.0)
    bars = int(math.ceil(seconds / bar_s))
    tom_len = int(0.5 * _SR)
    tom_env = np.exp(-np.linspace(0, 8, tom_len)).astype(np.float32)
    tom_freq = 70.0
    tom = _sine(tom_freq, tom_len / _SR) * tom_env
    for b in range(bars):
        start = int(b * bar_s * _SR)
        if start >= n:
            break
        seg = tom[: min(tom_len, n - start)]
        out[start:start + len(seg)] += seg * tom_gain

    # Gentle fade-out at the very end.
    out[-int(0.8 * _SR):] *= np.linspace(1, 0, int(0.8 * _SR), dtype=np.float32)

    beats = [round(i * beat_s, 4) for i in range(int(math.ceil(seconds / beat_s)))]
    return out, beats, bpm


def _duck(music: np.ndarray, voice: np.ndarray, cfg: Dict[str, Any]) -> np.ndarray:
    """Sidechain-ish ducking: reduce music gain while |voice| envelope is above threshold."""
    mcfg = cfg["music"]
    duck_lin = 10 ** (mcfg["duck_db"] / 20.0)  # <1
    attack = int(mcfg["duck_attack_ms"] / 1000.0 * _SR)
    release = int(mcfg["duck_release_ms"] / 1000.0 * _SR)

    n = min(len(music), len(voice))
    env = np.abs(voice[:n]).astype(np.float32)
    # Smoothed envelope.
    win = max(1, int(0.02 * _SR))
    kernel = np.ones(win, dtype=np.float32) / win
    env = np.convolve(env, kernel, mode="same")

    threshold = 0.02
    active = (env > threshold).astype(np.float32)
    gain = np.ones(n, dtype=np.float32)
    state = 1.0
    for i in range(n):
        if active[i] > 0.5:
            target = duck_lin
            step = (target - state) / max(1, attack)
            state += step if state > target else 0.0
        else:
            target = 1.0
            step = (target - state) / max(1, release)
            state += step if state < target else 0.0
        gain[i] = state

    out = music.copy()
    out[:n] *= gain
    if len(music) > n:
        out[n:] *= 1.0
    return out


def run(run_dir: Path, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = cfg or load_config()
    target = float(cfg["video"]["target_seconds"])

    voice_path = run_dir / "voice.wav"
    if not voice_path.is_file():
        raise RuntimeError("voice.wav not found; run the voice stage first.")
    voice = _read_wav_mono(voice_path)
    if len(voice) > int(target * _SR):
        # Voice longer than target: keep it; the renderer will still cap at target and
        # QA will catch a real overflow.
        voice_for_mix = voice[: int(target * _SR)]
    else:
        voice_for_mix = np.pad(voice, (0, int(target * _SR) - len(voice)))

    music, beats, bpm = _render_bed(cfg, target, seed=0)
    music = _duck(music, voice_for_mix, cfg)

    music_path = run_dir / "music.wav"
    _write_wav_mono(music_path, music)

    mix = music[: len(voice_for_mix)] + voice_for_mix
    # Normalize peak to -1 dBFS.
    peak = float(np.max(np.abs(mix))) or 1.0
    mix = mix / peak * 0.89
    mix_path = run_dir / "audio_mix.wav"
    _write_wav_mono(mix_path, mix)

    out = {
        "bpm": bpm,
        "duration_seconds": target,
        "beats": beats,
        "ducking_gain_db": cfg["music"]["duck_db"],
        "mood": "mysterious-minor",
    }
    (run_dir / "music.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _LOG.info("Music done: bpm=%d, %.1fs bed, duck=%.1fdB", bpm, target, cfg["music"]["duck_db"])
    return out