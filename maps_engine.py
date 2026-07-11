"""Google Maps embed helpers and location-intent detection for chat."""
from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional
from urllib.parse import quote

_LOCATION_HINTS = re.compile(
    r"("
    r"\u3069\u3053|\u5834\u6240|\u8fd1\u304f|\u6559\u3048\u3066|\u6848\u5185|\u884c\u304d\u65b9|"
    r"where\s+(is|are|can|do)|how\s+to\s+get|directions?|"
    r"nearest|location|map|"
    r"\u5730\u56f3|\u30de\u30c3\u30d7|"
    r"\u533a\u5f79\u6240|\u5e02\u5f79\u6240|\u5165\u7ba1|"
    r"ward\s+office|city\s+hall|bank|post\s+office|immigration"
    r")",
    re.IGNORECASE,
)

_PLACE_NOUNS = re.compile(
    r"("
    r"\u533a\u5f79\u6240|\u5e02\u5f79\u6240|\u5165\u7ba1|\u3086\u3046\u3061\u3087|\u90f5\u4fbf\u5c40|\u9280\u884c|"
    r"\u643a\u5e2f|\u75c5\u9662|"
    r"ward\s+office|city\s+hall|immigration|bank|post\s+office|hospital|clinic"
    r")",
    re.IGNORECASE,
)


def looks_like_location_query(message: str) -> bool:
    text = (message or "").strip()
    if len(text) < 2:
        return False
    return bool(_LOCATION_HINTS.search(text))


def _near_suffix(near: Optional[str]) -> str:
    near = (near or "").strip()
    if not near:
        return ""
    return f" near {near}" if re.search(r"[A-Za-z]", near) else f" {near}"


def build_maps_embed_url(
    query: str,
    *,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    api_key: Optional[str] = None,
) -> str:
    """Build an embeddable Google Maps URL (no API key required for basic search embed)."""
    q = (query or "").strip()
    if not q:
        q = "Japan"
    resolved_key = (api_key or os.getenv("GOOGLE_MAPS_API_KEY") or "").strip()
    if resolved_key:
        base = "https://www.google.com/maps/embed/v1/search"
        params = f"key={quote(resolved_key)}&q={quote(q)}"
        if latitude is not None and longitude is not None:
            params += f"&center={latitude},{longitude}"
        return f"{base}?{params}"

    if latitude is not None and longitude is not None:
        return (
            f"https://maps.google.com/maps?q={quote(q)}"
            f"&ll={latitude},{longitude}&z=15&output=embed"
        )
    return f"https://maps.google.com/maps?q={quote(q)}&z=15&output=embed"


def build_maps_open_url(query: str, *, latitude: Optional[float] = None, longitude: Optional[float] = None) -> str:
    q = (query or "").strip() or "Japan"
    if latitude is not None and longitude is not None:
        return f"https://www.google.com/maps/search/{quote(q)}/@{latitude},{longitude},15z"
    return f"https://www.google.com/maps/search/{quote(q)}"


def infer_maps_query(
    message: str,
    *,
    near: Optional[str] = None,
    school_info: Optional[Dict[str, Any]] = None,
    current_address: Optional[str] = None,
    focus_task_id: Optional[str] = None,
) -> str:
    """Heuristic query string when the model/tools are unavailable (mock mode)."""
    text = (message or "").strip()
    loc = (near or current_address or (school_info or {}).get("location") or "").strip()

    m = _PLACE_NOUNS.search(text)
    if m:
        place = m.group(0)
        return f"{place}{_near_suffix(loc)}".strip()

    task_queries = {
        "task_ward_office": "\u533a\u5f79\u6240",
        "task_bank": "\u3086\u3046\u3061\u3087\u9280\u884c",
        "task_phone": "\u643a\u5e2f\u30b7\u30e7\u30c3\u30d7",
        "task_immigration": "\u5165\u56fd\u7ba1\u7406\u5c40",
        "task_school_enroll": (school_info or {}).get("school_name") or "\u8a9e\u5b66\u6821",
    }
    if focus_task_id and focus_task_id in task_queries:
        return f"{task_queries[focus_task_id]}{_near_suffix(loc)}".strip()

    if loc:
        return f"{text} {loc}".strip()
    return text or "Japan"


def build_map_block(
    query: str,
    lang: str = "ja",
    *,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    label: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    titles = {
        "zh-TW": "\u5730\u5716",
        "en": "Map",
        "ja": "\u5730\u56f3",
    }
    open_labels = {
        "zh-TW": "\u5728 Google \u5730\u5716\u4e2d\u958b\u555f",
        "en": "Open in Google Maps",
        "ja": "Google\u30de\u30c3\u30d7\u3067\u958b\u304f",
    }
    lang_key = lang if lang in titles else "en"
    embed_url = build_maps_embed_url(query, latitude=latitude, longitude=longitude, api_key=api_key)
    open_url = build_maps_open_url(query, latitude=latitude, longitude=longitude)
    return {
        "type": "map_embed",
        "title": titles[lang_key],
        "label": label or query,
        "query": query,
        "embed_url": embed_url,
        "open_url": open_url,
    }
