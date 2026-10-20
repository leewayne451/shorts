"""Fact-check stage.

For each scene in script.json that declares `claims`, retrieve supporting text from the
free Wikipedia API and ask Groq for a verdict: pass | soften | fail.

- Speculative beats with empty `claims` are exempt (verdict "speculative").
- On "soften" we rewrite the scene caption more cautiously and save the rewrite.
- On "fail" the orchestrator retries with a new subject (up to 3 attempts).

Output: factcheck.json
{
  "subject": str,
  "verdicts": [
    {"scene_index": int, "claim": str, "verdict": "pass"|"soften"|"fail"|"speculative",
     "reason": str, "sources": [url, ...], "rewrite": str | null}
  ],
  "overall": "pass" | "soften" | "fail" | "exempt",
  "rewritten_captions": { "<scene_index>": "<new caption>" }
}
"""
from __future__ import annotations

import json
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from whatif import get_logger, load_config
from whatif.llm import GroqError, chat_json

_LOG = get_logger("whatif.factcheck")

_WIKI_API = "https://en.wikipedia.org/w/api.php"
_WIKI_TIMEOUT = 15.0
_WIKI_MAX_CHARS_PER_CLAIM = 1200
_WIKI_MAX_CLAIMS = 12


_SYSTEM_PROMPT = """You are a careful fact-checker for a speculative "What if X vanished?"
short-video series. You will be given a scene claim and a short passage retrieved from Wikipedia.
You must return a single strict JSON object, no prose.

For each claim, output one object:
{
  "verdict": "pass" | "soften" | "fail",
  "reason": "<one short sentence>",
  "rewrite": "<a cautious rewrite of the claim, or null if verdict is pass>",
  "sources": ["<wikipedia url>", ...]
}

Guidance:
- "pass": the Wikipedia passage clearly supports the claim as stated.
- "soften": the claim is directionally plausible but overstated; provide a more cautious
  rewrite that the passage supports. Keep the rewrite under 25 words.
- "fail": the passage contradicts the claim, or the claim depends on a specific fine, price,
  precise statistic, or named entity that the passage does not support.

If the passage is empty or irrelevant, prefer "soften" with a hedged rewrite over "fail",
UNLESS the claim makes a specific numeric or named-entity assertion, in which case "fail".
"""


def _wiki_search(query: str) -> Optional[str]:
    """Return the title of the top Wikipedia search hit for `query`, or None."""
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": 1,
        "format": "json",
        "utf8": 1,
    }
    try:
        r = requests.get(_WIKI_API, params=params, timeout=_WIKI_TIMEOUT,
                         headers={"User-Agent": "whatif-shorts/1.0 (factcheck)"})
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        _LOG.warning("Wikipedia search failed for %r: %s", query, e)
        return None
    hits = data.get("query", {}).get("search", [])
    if not hits:
        return None
    return hits[0].get("title")


def _wiki_extract(title: str) -> str:
    """Return the plain-text extract for a Wikipedia page title, or ''."""
    params = {
        "action": "query",
        "prop": "extracts",
        "explaintext": 1,
        "exintro": 0,
        "titles": title,
        "format": "json",
        "utf8": 1,
        "redirects": 1,
    }
    try:
        r = requests.get(_WIKI_API, params=params, timeout=_WIKI_TIMEOUT,
                         headers={"User-Agent": "whatif-shorts/1.0 (factcheck)"})
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        _LOG.warning("Wikipedia extract failed for %r: %s", title, e)
        return ""
    pages = data.get("query", {}).get("pages", {})
    for _, page in pages.items():
        extract = page.get("extract") or ""
        return extract[:_WIKI_MAX_CHARS_PER_CLAIM]
    return ""


def _page_url(title: str) -> str:
    return "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))


def _retrieve_context(claim: str) -> tuple[str, List[str]]:
    """Return (context_text, source_urls) for a claim."""
    title = _wiki_search(claim)
    if not title:
        return "", []
    extract = _wiki_extract(title)
    return extract, [_page_url(title)]


def _verdict_for_claim(
    cfg: Dict[str, Any], claim: str, context: str, sources: List[str]
) -> Dict[str, Any]:
    user = (
        f"Claim: {claim!r}\n\n"
        f"Wikipedia passage (may be empty):\n\"\"\"\n{context}\n\"\"\"\n\n"
        f"Known source URLs: {sources}\n\n"
        f"Return the JSON object now."
    )
    try:
        data = chat_json(
            cfg,
            system=_SYSTEM_PROMPT,
            user=user,
            temperature=cfg["groq"]["temperature_factcheck"],
            max_tokens=512,
        )
    except GroqError as e:
        _LOG.warning("Factcheck LLM failed for claim %r: %s", claim, e)
        return {"verdict": "soften", "reason": f"factcheck LLM error: {e}",
                "rewrite": claim, "sources": sources}

    verdict = (data.get("verdict") or "").strip().lower()
    if verdict not in {"pass", "soften", "fail"}:
        verdict = "soften"
    reason = str(data.get("reason") or "").strip()
    rewrite = data.get("rewrite")
    if verdict != "soften":
        rewrite = None
    elif not isinstance(rewrite, str) or not rewrite.strip():
        rewrite = claim
    srcs = data.get("sources")
    if not isinstance(srcs, list):
        srcs = sources
    return {"verdict": verdict, "reason": reason, "rewrite": rewrite, "sources": list(srcs)}


def run(
    subject: str,
    script: Dict[str, Any],
    run_dir: Path,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run the factcheck stage, writing factcheck.json in run_dir."""
    cfg = cfg or load_config()
    scenes = script["scenes"]

    verdicts: List[Dict[str, Any]] = []
    rewritten: Dict[str, str] = {}
    checked = 0

    for scene in scenes:
        claims = scene.get("claims") or []
        if not claims:
            continue
        for claim in claims:
            if checked >= _WIKI_MAX_CLAIMS:
                _LOG.warning("Hit max claims (%d); skipping further fact checks.", _WIKI_MAX_CLAIMS)
                break
            checked += 1
            ctx, srcs = _retrieve_context(claim)
            v = _verdict_for_claim(cfg, claim, ctx, srcs)
            verdicts.append({
                "scene_index": scene["index"],
                "claim": claim,
                **v,
            })
            if v["verdict"] == "soften" and v.get("rewrite"):
                # Keep only the first soften rewrite per scene to avoid clobbering.
                rewritten.setdefault(str(scene["index"]), v["rewrite"])

    if not verdicts:
        overall = "exempt"
    elif any(v["verdict"] == "fail" for v in verdicts):
        overall = "fail"
    elif any(v["verdict"] == "soften" for v in verdicts):
        overall = "soften"
    else:
        overall = "pass"

    out = {
        "subject": subject,
        "verdicts": verdicts,
        "overall": overall,
        "rewritten_captions": rewritten,
    }
    (run_dir / "factcheck.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _LOG.info("Factcheck overall=%s (%d claims checked)", overall, len(verdicts))
    return out


def load(run_dir: Path) -> Dict[str, Any]:
    return json.loads((run_dir / "factcheck.json").read_text(encoding="utf-8"))