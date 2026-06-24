"""Lightweight i18n — JSON locale files keyed by dot-path."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..config import DATA_DIR, TUNABLES

log = logging.getLogger("services.i18n")

_LOCALES_DIR = DATA_DIR / "locales"
# Bundled with the firmware package (used when DATA_DIR is a sandbox without locales/).
_BUNDLED_LOCALES_DIR = Path(__file__).resolve().parents[3] / "data" / "locales"
_cache: dict[str, dict[str, str]] = {}


def _locales_dir() -> Path:
    if (_LOCALES_DIR / "en.json").exists():
        return _LOCALES_DIR
    return _BUNDLED_LOCALES_DIR


def _load_lang(lang: str) -> dict[str, str]:
    if lang in _cache:
        return _cache[lang]
    base = _locales_dir()
    path = base / f"{lang}.json"
    fallback_path = base / "en.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        try:
            raw = json.loads(fallback_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
    _cache[lang] = {str(k): str(v) for k, v in raw.items()}
    return _cache[lang]


def reload_locales() -> None:
    _cache.clear()


def t(key: str, **kwargs: object) -> str:
    lang = (TUNABLES.language or "en").strip().lower()
    if lang not in ("en", "ro"):
        lang = "en"
    table = _load_lang(lang)
    if key not in table and lang != "en":
        table = _load_lang("en")
    text = table.get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text
