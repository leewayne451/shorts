"""Groq LLM wrapper (plain HTTPS via requests, no SDK).

Provides:
- chat_json(...) -> dict : request a strict JSON object (JSON mode where supported),
  with robust extraction from code fences / prose wrappers.
- chat_text(...) -> str : plain text completion (used nowhere in v1, kept for
  future use and for the factcheck fallback if JSON mode fails).

Rate-limit handling:
- Exponential backoff on connection errors, 5xx, and 429.
- Honors Retry-After header on 429 (seconds or HTTP-date).
- Caps total retries at cfg["groq"]["max_retries"].
"""
from __future__ import annotations

import json
import time
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional

import requests

from whatif import get_logger

_LOG = get_logger("whatif.llm")


class GroqError(RuntimeError):
    """Raised when the Groq API cannot be used after retries."""


def _api_key() -> str:
    import os
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        raise GroqError(
            "GROQ_API_KEY is not set. Create a free key at "
            "https://console.groq.com/keys and add it as a repo secret or env var."
        )
    return key


def _retry_after_seconds(headers: requests.structures.CaseInsensitiveDict) -> Optional[float]:
    ra = headers.get("Retry-After")
    if not ra:
        return None
    ra = ra.strip()
    try:
        return max(0.0, float(ra))
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(ra)
        return max(0.0, dt.timestamp() - time.time())
    except Exception:
        return None


def _post(cfg: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    gcfg = cfg["groq"]
    url = gcfg["base_url"]
    max_retries = int(gcfg["max_retries"])
    timeout = float(gcfg["timeout_seconds"])
    base = float(gcfg["backoff_base_seconds"])
    cap = float(gcfg["backoff_max_seconds"])

    headers = {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except requests.RequestException as e:
            last_err = e
            sleep_s = min(cap, base * (2 ** attempt))
            _LOG.warning("Groq request error (%s); retry in %.1fs", e, sleep_s)
            time.sleep(sleep_s)
            continue

        if resp.status_code == 429:
            wait_s = _retry_after_seconds(resp.headers) or min(cap, base * (2 ** attempt))
            _LOG.warning("Groq 429 rate limit; waiting %.1fs", wait_s)
            time.sleep(wait_s)
            last_err = GroqError("rate limited")
            continue

        if resp.status_code >= 500:
            sleep_s = min(cap, base * (2 ** attempt))
            _LOG.warning("Groq %d; retry in %.1fs", resp.status_code, sleep_s)
            time.sleep(sleep_s)
            last_err = GroqError(f"server {resp.status_code}")
            continue

        if resp.status_code >= 400:
            # 4xx other than 429: don't retry blindly; surface the body.
            raise GroqError(
                f"Groq API error {resp.status_code}: {resp.text[:500]}"
            )

        try:
            return resp.json()
        except ValueError as e:
            raise GroqError(f"Groq returned non-JSON body: {e}") from e

    raise GroqError(f"Groq request failed after {max_retries} retries: {last_err}")


def chat_text(
    cfg: Dict[str, Any],
    system: str,
    user: str,
    temperature: Optional[float] = None,
    max_tokens: int = 1024,
) -> str:
    """Plain-text completion. Returns the assistant message content."""
    gcfg = cfg["groq"]
    payload: Dict[str, Any] = {
        "model": gcfg["model"],
        "temperature": gcfg["temperature_script"] if temperature is None else temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    data = _post(cfg, payload)
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as e:
        raise GroqError(f"Unexpected Groq response shape: {data}") from e


def _extract_json_object(text: str) -> Dict[str, Any]:
    """Extract the outermost JSON object from text, tolerating code fences and prose."""
    if not text:
        raise GroqError("Empty LLM content; cannot extract JSON.")
    s = text.strip()
    if s.startswith("```"):
        # Strip a leading fence of the form ``` or ```json
        first_newline = s.find("\n")
        if first_newline != -1:
            s = s[first_newline + 1:]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
        s = s.strip()
    # Find first { and last } as a robust outermost-object heuristic.
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise GroqError(f"No JSON object found in LLM output: {text[:400]!r}")
    candidate = s[start:end + 1]
    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError as e:
        raise GroqError(f"Invalid JSON from LLM: {e}: {candidate[:400]!r}") from e
    if not isinstance(obj, dict):
        raise GroqError(f"LLM JSON root is not an object: {type(obj).__name__}")
    return obj


def chat_json(
    cfg: Dict[str, Any],
    system: str,
    user: str,
    temperature: Optional[float] = None,
    max_tokens: int = 4096,
    json_mode: bool = True,
) -> Dict[str, Any]:
    """Request a strict JSON object. Uses JSON mode when supported by the model."""
    gcfg = cfg["groq"]
    payload: Dict[str, Any] = {
        "model": gcfg["model"],
        "temperature": gcfg["temperature_script"] if temperature is None else temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    data = _post(cfg, payload)
    try:
        content = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as e:
        raise GroqError(f"Unexpected Groq response shape: {data}") from e
    return _extract_json_object(content)


def build_retry_user_prompt(base_user: str, error_message: str) -> str:
    """Append the previous validation error to the user prompt for the retry loop."""
    return (
        f"{base_user}\n\n"
        f"---\n"
        f"Your previous reply failed validation with this error:\n"
        f"{error_message}\n\n"
        f"Return ONLY a corrected JSON object satisfying every constraint. "
        f"Do not wrap it in prose. Do not include code fences."
    )