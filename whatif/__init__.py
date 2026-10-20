"""whatif-shorts — "What if X vanished?" short video generator.

Package entrypoint. Also hosts load_config(), the single source of truth for
configuration loading across all stages. There is deliberately no config.py.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict

import yaml

__version__ = "1.0.0"

_LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s :: %(message)s"
_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"

# Repo root: this file lives at <root>/whatif/__init__.py
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.yaml"


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger, idempotently."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_LOG_FORMAT, _LOG_DATEFMT))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def load_config(path: str | os.PathLike[str] | None = None) -> Dict[str, Any]:
    """Load config.yaml (or `path`), resolve relative paths against REPO_ROOT,
    and return a plain dict.

    Relative paths in config are NOT rewritten; callers should join with
    REPO_ROOT when they touch the filesystem. `paths.runs_dir` etc. are
    relative by design so the repo stays portable.
    """
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not cfg_path.is_file():
        raise FileNotFoundError(f"Config file not found: {cfg_path}")
    with cfg_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict):
        raise ValueError(f"Config root must be a mapping, got {type(cfg).__name__}")
    return cfg


def resolve_path(relative_or_absolute: str | os.PathLike[str]) -> Path:
    """Resolve a path from config/CLI against REPO_ROOT if it is relative."""
    p = Path(relative_or_absolute)
    return p if p.is_absolute() else (REPO_ROOT / p)