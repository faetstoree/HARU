"""Backend i18n helpers — load locale JSON packs and provide a t() translation function.

Locale files live in:  static/locales/backend/{lang}.json
Supported languages:   zh-TW  |  en  |  ja
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

_LOCALES_DIR = os.path.join(
    os.path.dirname(__file__), "data", "locales", "backend"
)
_SUPPORTED = ("zh-TW", "en", "ja")
_cache: Dict[str, Dict[str, str]] = {}


def _load(lang: str) -> Dict[str, str]:
    if lang not in _cache:
        path = os.path.join(_LOCALES_DIR, f"{lang}.json")
        try:
            with open(path, encoding="utf-8") as f:
                _cache[lang] = json.load(f)
        except FileNotFoundError:
            _cache[lang] = {}
    return _cache[lang]


def normalize_backend_lang(lang: str) -> str:
    return lang if lang in _SUPPORTED else "en"


def t(key: str, lang: str, **kwargs: Any) -> str:
    """Return the translated string for *key* in *lang*.

    Falls back to 'en' if the key is missing in the requested language.
    Any extra keyword arguments are interpolated with str.format_map().

    Example::

        t("chipComplete", "ja")               # → "完了にする"
        t("pdfDuration", "en", n=30)          # → "~30 min"
        t("greetingBody", "zh-TW",
          location="東京都文京區",
          school_name="語言學校",
          completed=2, total=8)
    """
    lang = normalize_backend_lang(lang)
    pack = _load(lang)
    text = pack.get(key)
    if text is None:
        # fallback to English
        text = _load("en").get(key, key)
    if kwargs:
        try:
            text = text.format_map(kwargs)
        except (KeyError, IndexError):
            pass
    return text


# Mapping from option value codes to locale key names
_JAPANESE_LEVEL_KEYS: Dict[str, str] = {
    "beginner_zero": "japaneseLevelBeginner_zero",
    "beginner":      "japaneseLevelBeginner",
    "intermediate":  "japaneseLevelIntermediate",
    "advanced":      "japaneseLevelAdvanced",
}


def japanese_level_label(code: str, lang: str) -> str:
    """Convert a japanese_level code stored in DB to a human-readable label.

    Used when injecting the student's level into AI prompts so the model
    receives a descriptive string rather than a bare code.

    Example::

        japanese_level_label("intermediate", "en")  # → "Intermediate (approx. N3~N2)"
        japanese_level_label("beginner_zero", "ja") # → "未学習（全く話せない）"
    """
    key = _JAPANESE_LEVEL_KEYS.get(code)
    if key:
        return t(key, lang)
    # Legacy values that may still exist in DB before migration
    _legacy: Dict[str, str] = {
        "零基礎": "beginner_zero",
        "初級":   "beginner",
        "中級":   "intermediate",
        "高級":   "advanced",
    }
    mapped = _legacy.get(code)
    if mapped:
        return t(_JAPANESE_LEVEL_KEYS[mapped], lang)
    return code  # unknown code, return as-is
