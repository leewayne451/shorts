"""CLI orchestrator for whatif-shorts.

Usage:
    python -m whatif.run --subject "bees"
    python -m whatif.run --topic "bees"            # alias
    python -m whatif.run --subject "bees" --dry-run
    python -m whatif.run --subject "bees" --from-stage render
    python -m whatif.run                            # next unused subject from subjects.txt

Stages: topic -> script -> factcheck -> voice -> music -> render -> qa -> publish
Each stage is idempotent and writes its outputs into the run folder.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from whatif import REPO_ROOT, get_logger, load_config, resolve_path

_LOG = get_logger("whatif.run")

STAGES = ["topic", "script", "factcheck", "voice", "music", "render", "qa", "publish"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _slugify(text: str) -> str:
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "subject"


def _new_run_dir(cfg: Dict[str, Any], subject: str) -> Path:
    runs_dir = resolve_path(cfg["paths"]["runs_dir"])
    runs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    slug = _slugify(subject)
    run_dir = runs_dir / f"{stamp}-what-if-{slug}-vanished"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _read_subjects(cfg: Dict[str, Any]) -> list[str]:
    path = resolve_path(cfg["paths"]["subjects_file"])
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    return [ln for ln in lines if ln and not ln.startswith("#")]


def _read_used(cfg: Dict[str, Any]) -> set[str]:
    path = resolve_path(cfg["paths"]["used_subjects_file"])
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    if isinstance(data, list):
        return {str(x) for x in data}
    if isinstance(data, dict):
        return {str(k) for k in data.keys()}
    return set()


def _write_used(cfg: Dict[str, Any], used: set[str]) -> None:
    path = resolve_path(cfg["paths"]["used_subjects_file"])
    path.write_text(json.dumps(sorted(used), indent=2, ensure_ascii=False), encoding="utf-8")


def _pick_next_subject(cfg: Dict[str, Any]) -> str:
    subjects = _read_subjects(cfg)
    used = _read_used(cfg)
    for s in subjects:
        if s not in used:
            return s
    # All used: recycle the least recently used by simply taking the first.
    _LOG.warning("All subjects have been used; recycling the first subject.")
    if not subjects:
        raise RuntimeError("subjects.txt is empty; add at least one subject.")
    return subjects[0]


def _log_stage(stage: str, phase: str, t0: float) -> None:
    _LOG.info("[%s] %s (%.1fs elapsed)", stage, phase, time.time() - t0)


# ---------------------------------------------------------------------------
# Stage dispatchers
# ---------------------------------------------------------------------------
def _stage_topic(args: argparse.Namespace, cfg: Dict[str, Any]) -> str:
    subject = (args.subject or args.topic or "").strip()
    if not subject:
        env = os.environ.get("WHATIF_SUBJECT", "").strip()
        subject = env if env else _pick_next_subject(cfg)
    if not subject:
        raise RuntimeError("Could not determine a subject. Pass --subject or fill subjects.txt.")
    _LOG.info("Chosen subject: %r", subject)
    return subject


def _stage_script(subject: str, run_dir: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    from whatif import script_stage
    return script_stage.run(subject, run_dir, cfg)


def _stage_factcheck(
    subject: str, script: Dict[str, Any], run_dir: Path, cfg: Dict[str, Any]
) -> Dict[str, Any]:
    from whatif import factcheck
    fc = factcheck.run(subject, script, run_dir, cfg)
    # Apply soften rewrites to captions in-place and re-save script.json.
    rewritten = fc.get("rewritten_captions") or {}
    if rewritten:
        changed = False
        for scene in script["scenes"]:
            key = str(scene["index"])
            if key in rewritten:
                scene["caption"] = rewritten[key]
                changed = True
        if changed:
            (run_dir / "script.json").write_text(
                json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            _LOG.info("Applied %d softened rewrite(s) to script.json", len(rewritten))
    return fc


def _stage_voice(script: Dict[str, Any], run_dir: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    from whatif import voice
    return voice.run(script, run_dir, cfg)


def _stage_music(run_dir: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    from whatif import music
    return music.run(run_dir, cfg)


def _stage_render(script: Dict[str, Any], run_dir: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    from whatif.render import engine
    return engine.run(script, run_dir, cfg)


def _stage_qa(run_dir: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    from whatif import qa
    return qa.run(run_dir, cfg)


def _stage_publish(
    script: Dict[str, Any], factcheck_result: Dict[str, Any], run_dir: Path,
    cfg: Dict[str, Any], dry_run: bool,
) -> Dict[str, Any]:
    from whatif import publish
    return publish.run(script, factcheck_result, run_dir, cfg, dry_run=dry_run)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m whatif.run", description="whatif-shorts CLI")
    p.add_argument("--subject", help="Thing that vanishes, e.g. 'bees'")
    p.add_argument("--topic", help="Alias for --subject (kept for compatibility)")
    p.add_argument("--from-stage", choices=STAGES, default="topic",
                   help="Resume from this stage (earlier stages are skipped)")
    p.add_argument("--run-dir", help="Existing run folder to resume into (optional)")
    p.add_argument("--dry-run", action="store_true", help="Skip Telegram upload")
    p.add_argument("--config", help="Path to config.yaml override")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    cfg = load_config(args.config)

    # Locate or create the run dir.
    if args.run_dir:
        run_dir = Path(args.run_dir).resolve()
        if not run_dir.is_dir():
            print(f"ERROR: --run-dir does not exist: {run_dir}", file=sys.stderr)
            return 2
        # Recover subject from existing script.json if present, else CLI subject.
        subject = (args.subject or args.topic or "").strip()
        if not subject:
            sj = run_dir / "script.json"
            if sj.is_file():
                subject = json.loads(sj.read_text(encoding="utf-8")).get("opening_question", "")
                m = re.match(r"^\s*what\s+if\s+(.+?)\s+vanished\?", subject, re.I)
                if m:
                    subject = m.group(1)
    else:
        subject = _stage_topic(args, cfg)
        run_dir = _new_run_dir(cfg, subject)

    _LOG.info("Run directory: %s", run_dir)

    start_index = STAGES.index(args.from_stage)
    script: Optional[Dict[str, Any]] = None
    fc: Optional[Dict[str, Any]] = None

    # topic
    if start_index <= STAGES.index("topic"):
        t0 = time.time()
        _log_stage("topic", f"start subject={subject!r}", t0)
        _log_stage("topic", "done", t0)
        used = _read_used(cfg)
        used.add(subject)
        _write_used(cfg, used)

    # script
    if start_index <= STAGES.index("script"):
        t0 = time.time()
        _log_stage("script", "start", t0)
        script = _stage_script(subject, run_dir, cfg)
        _log_stage("script", "done", t0)
    else:
        from whatif import script_stage
        script = script_stage.load(run_dir)

    # factcheck (with topic-retry loop)
    if start_index <= STAGES.index("factcheck"):
        t0 = time.time()
        _log_stage("factcheck", "start", t0)
        attempts = 0
        while True:
            attempts += 1
            fc = _stage_factcheck(subject, script, run_dir, cfg)
            if fc["overall"] in {"pass", "soften", "exempt"}:
                break
            if attempts >= 3:
                print(
                    "ERROR: factcheck failed 3 times; refusing to publish. "
                    "Check factcheck.json for details.",
                    file=sys.stderr,
                )
                return 3
            _LOG.warning("Factcheck failed; retrying with a new subject (attempt %d/3).", attempts)
            subject = _pick_next_subject(cfg)
            _LOG.info("New subject: %r", subject)
            script = _stage_script(subject, run_dir, cfg)
        _log_stage("factcheck", "done", t0)
    else:
        from whatif import factcheck
        fc = factcheck.load(run_dir)

    # voice
    if start_index <= STAGES.index("voice"):
        t0 = time.time()
        _log_stage("voice", "start", t0)
        _stage_voice(script, run_dir, cfg)
        _log_stage("voice", "done", t0)

    # music
    if start_index <= STAGES.index("music"):
        t0 = time.time()
        _log_stage("music", "start", t0)
        _stage_music(run_dir, cfg)
        _log_stage("music", "done", t0)

    # render
    if start_index <= STAGES.index("render"):
        t0 = time.time()
        _log_stage("render", "start", t0)
        _stage_render(script, run_dir, cfg)
        _log_stage("render", "done", t0)

    # qa
    if start_index <= STAGES.index("qa"):
        t0 = time.time()
        _log_stage("qa", "start", t0)
        qa_result = _stage_qa(run_dir, cfg)
        _log_stage("qa", "done", t0)
        if not qa_result.get("pass", False):
            print(f"ERROR: QA failed: {qa_result.get('reason', 'unknown')}", file=sys.stderr)
            return 4

    # publish
    if start_index <= STAGES.index("publish"):
        t0 = time.time()
        _log_stage("publish", "start", t0)
        _stage_publish(script, fc, run_dir, cfg, dry_run=args.dry_run)
        _log_stage("publish", "done", t0)

    _LOG.info("Done. Run folder: %s", run_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())