"""School search for onboarding autocomplete."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict, List

from roadmap_engine import normalize_lang, pick_i18n

SCHOOLS_PATH = os.path.join(os.path.dirname(__file__), "data", "schools.json")


@lru_cache(maxsize=1)
def load_schools() -> Dict[str, Any]:
    with open(SCHOOLS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _school_label(school: Dict[str, Any], lang: str) -> str:
    return pick_i18n(school.get("name", {}), lang)


def search_schools(query: str = "", lang: str = "en", limit: int = 25) -> List[Dict[str, Any]]:
    lang = normalize_lang(lang)
    data = load_schools()
    q = (query or "").strip().lower()
    tokens = [t for t in q.split() if t]
    results = []
    for school in data.get("schools", []):
        label = _school_label(school, lang)
        names = school.get("name", {})
        haystack = " ".join([
            label,
            names.get("zh-TW", ""),
            names.get("en", ""),
            names.get("ja", ""),
            school.get("location", ""),
            school.get("city", ""),
            school.get("prefecture", ""),
            school.get("id", ""),
        ]).lower()
        if q:
            if q not in haystack and not all(t in haystack for t in tokens):
                continue
        label_lower = label.lower()
        if not q:
            rank = (school.get("prefecture", ""), label)
        else:
            rank = (
                0 if label_lower.startswith(q) else
                1 if q in label_lower else
                2 if q in haystack else 3,
                label,
            )
        results.append((rank, {
            "id": school["id"],
            "label": label,
            "location": school.get("location", ""),
            "city": school.get("city", ""),
            "prefecture": school.get("prefecture", ""),
            "type": school.get("type", "language_school"),
        }))
    results.sort(key=lambda x: (x[0][0], x[0][1]))
    return [item for _, item in results[:limit]]
