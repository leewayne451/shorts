"""Publish stage: Telegram sendVideo + follow-up text (sources, credits, disclosure).

- Always uploads nothing here; the workflow handles the GitHub Actions artifact.
- If TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set and dry_run is False, sends the video
  for human approval, then sends a second plain-text message with full beat captions, verdicts,
  sources, photo credits, and the AI-disclosure note. If split_caption is False, only sends
  the short caption on the video.
- Truncates the video caption to cfg["telegram"]["caption_max_chars"] (1024).
- Never fails the run on Telegram errors; logs a warning and returns {"sent": False, ...}.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from whatif import get_logger, load_config

_LOG = get_logger("whatif.publish")
_TIMEOUT = 60.0


def _api(base: str, token: str, method: str) -> str:
    return f"{base}/bot{token}/{method}"


def _video_caption(script: Dict[str, Any], factcheck: Dict[str, Any],
                   max_chars: int) -> str:
    opening = script["opening_question"]
    first_beat = ""
    if len(script["scenes"]) > 1:
        first_beat = script["scenes"][1]["caption"]
    verdict = factcheck.get("overall", "exempt")
    parts = [opening]
    if first_beat:
        parts.append(first_beat)
    parts.append(f"[factcheck: {verdict}]")
    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[: max_chars - 3].rstrip() + "..."
    return text


def _followup_text(script: Dict[str, Any], factcheck: Dict[str, Any],
                   credits: List[Dict[str, str]]) -> str:
    lines: List[str] = []
    lines.append("Full beat captions:")
    for scene in script["scenes"]:
        label = "OPENING" if scene.get("time_label") == "opening" else scene.get("time_label", "")
        lines.append(f"- [{label}] {scene['caption']}")
    lines.append("")
    lines.append("Fact-check:")
    for v in factcheck.get("verdicts", []) or []:
        lines.append(f"- scene {v['scene_index']}: {v['verdict']} — {v['claim'][:120]}")
    srcs: List[str] = []
    for v in factcheck.get("verdicts", []) or []:
        for s in v.get("sources", []) or []:
            if s and s not in srcs:
                srcs.append(s)
    if srcs:
        lines.append("")
        lines.append("Sources:")
        for s in srcs:
            lines.append(f"- {s}")
    if credits:
        lines.append("")
        lines.append("Photos from Pixabay:")
        for c in credits:
            lines.append(f"- {c.get('user','?')} — {c.get('page_url','')}")
    lines.append("")
    lines.append("Voice and visuals are AI-generated.")
    text = "\n".join(lines)
    if len(text) > 4096:
        text = text[:4090].rstrip() + "..."
    return text


def _load_credits(run_dir: Path) -> List[Dict[str, str]]:
    p = run_dir / "credits.json"
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def run(
    script: Dict[str, Any],
    factcheck: Dict[str, Any],
    run_dir: Path,
    cfg: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    cfg = cfg or load_config()
    video = run_dir / "final.mp4"
    if not video.is_file():
        raise RuntimeError("final.mp4 not found; run the render stage first.")

    tcfg = cfg["telegram"]
    base = tcfg["api_base"]
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if dry_run:
        _LOG.info("dry_run=True; skipping Telegram.")
        return {"sent": False, "reason": "dry_run"}

    if not token or not chat_id:
        _LOG.warning("Telegram credentials not set; skipping send.")
        return {"sent": False, "reason": "missing_credentials"}

    caption = _video_caption(script, factcheck, int(tcfg["caption_max_chars"]))
    credits = _load_credits(run_dir)

    result: Dict[str, Any] = {"sent": False}

    try:
        with video.open("rb") as f:
            r = requests.post(
                _api(base, token, "sendVideo"),
                data={
                    "chat_id": chat_id,
                    "caption": caption,
                    "supports_streaming": "true",
                },
                files={"video": (video.name, f, "video/mp4")},
                timeout=_TIMEOUT,
            )
        if r.status_code >= 400:
            _LOG.warning("Telegram sendVideo HTTP %d: %s", r.status_code, r.text[:400])
            return {"sent": False, "reason": f"sendVideo_http_{r.status_code}"}
        result["sent"] = True
        result["video_caption"] = caption
    except requests.RequestException as e:
        _LOG.warning("Telegram sendVideo failed: %s", e)
        return {"sent": False, "reason": f"sendVideo_exception: {e}"}

    if tcfg["split_caption"]:
        follow = _followup_text(script, factcheck, credits)
        try:
            r2 = requests.post(
                _api(base, token, "sendMessage"),
                data={"chat_id": chat_id, "text": follow, "disable_web_page_preview": "true"},
                timeout=_TIMEOUT,
            )
            if r2.status_code >= 400:
                _LOG.warning("Telegram sendMessage HTTP %d: %s", r2.status_code, r2.text[:400])
                result["followup_sent"] = False
            else:
                result["followup_sent"] = True
        except requests.RequestException as e:
            _LOG.warning("Telegram sendMessage failed: %s", e)
            result["followup_sent"] = False

    _LOG.info("Telegram send complete: sent=%s followup=%s",
              result.get("sent"), result.get("followup_sent"))
    return result