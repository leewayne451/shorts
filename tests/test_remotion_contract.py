"""Regression checks for the Python-to-Remotion audio contract."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_remotion_audio_uses_static_file_for_staged_assets():
    source = (ROOT / "remotion" / "AudioLayer.tsx").read_text(encoding="utf-8")
    assert "staticFile" in source
    assert "audioSrc(manifest.audioPath)" in source


def test_python_bridge_stages_audio_under_public_assets():
    source = (ROOT / "whatif" / "render" / "remotion.py").read_text(encoding="utf-8")
    assert 'REPO_ROOT / "public" / "whatif-audio"' in source
    assert '"audioPath": f"/whatif-audio/{public_audio_name}"' in source


def test_python_bridge_requires_audio_mux():
    source = (ROOT / "whatif" / "render" / "remotion.py").read_text(encoding="utf-8")
    assert "_mux_audio(ffmpeg, output, audio_path)" in source
    assert '"-map", "1:a:0"' in source
