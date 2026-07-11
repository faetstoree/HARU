"""Official resource DB resolver and link_chips block builder."""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from roadmap_engine import normalize_lang, pick_i18n, profile_from_dict
from task_id_aliases import task_ids_overlap
from backend_i18n import t

RESOURCES_PATH = os.path.join(os.path.dirname(__file__), "data", "official_resources.json")
WARDS_PATH = os.path.join(os.path.dirname(__file__), "data", "regional_wards.json")

ALLOWED_TIERS = {"official", "semi_official"}


@lru_cache(maxsize=1)
def load_resources() -> Dict[str, Any]:
    with open(RESOURCES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_wards() -> Dict[str, Any]:
    if not os.path.exists(WARDS_PATH):
        return {"wards": {}}
    with open(WARDS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _parse_ward_from_location(location: Optional[str]) -> Optional[str]:
    if not location:
        return None
    loc_norm = location.replace("區", "区")
    wards = load_wards().get("wards", {})
    for ward_key in wards:
        if ward_key in loc_norm or ward_key in location:
            return ward_key
    m = re.search(r"([\u4e00-\u9fff]{1,4})区", loc_norm)
    if m:
        candidate = m.group(1) + "区"
        if candidate in wards:
            return candidate
    return None


def _resolve_resource_url(resource: Dict[str, Any], profile: Dict[str, Any]) -> Optional[str]:
    if resource.get("resolver") == "ward_office":
        ward = _parse_ward_from_location(profile.get("location"))
        if ward:
            ward_data = load_wards().get("wards", {}).get(ward)
            if ward_data:
                return ward_data.get("url")
        loc = profile.get("location") or ""
        if loc:
            return f"https://www.google.com/search?q={quote(loc + ' 区役所 公式')}"
        return None
    url = resource.get("url") or ""
    return url if url else None


def _resolve_resource_label(resource: Dict[str, Any], profile: Dict[str, Any], lang: str) -> str:
    lang = normalize_lang(lang)
    if resource.get("resolver") == "ward_office":
        ward = _parse_ward_from_location(profile.get("location"))
        if ward:
            ward_data = load_wards().get("wards", {}).get(ward, {})
            ward_name = pick_i18n(ward_data.get("name", {}), lang)
            return f"{ward_name}{t('wardLinkSuffix', lang)}"
    return pick_i18n(resource.get("title", {}), lang)


def profile_with_location(data: Dict[str, Any]) -> Dict[str, Any]:
    profile = profile_from_dict(data)
    profile["location"] = data.get("location")
    return profile


def resolve_resources_for_task(
    task_id: str,
    profile: Dict[str, Any],
    lang: str = "zh-TW",
    limit: int = 4,
) -> List[Dict[str, Any]]:
    """Return link chip items for a task."""
    if "housing_type" not in profile:
        profile = profile_with_location(profile)
    lang = normalize_lang(lang)
    data = load_resources()
    matches = []
    for res in data.get("resources", []):
        if not task_ids_overlap(task_id, res.get("task_ids") or []):
            continue
        if res.get("tier") not in ALLOWED_TIERS:
            continue
        url = _resolve_resource_url(res, profile)
        if not url:
            continue
        matches.append({
            "resource_id": res["id"],
            "label": _resolve_resource_label(res, profile, lang),
            "url": url,
            "tier": res.get("tier", "official"),
            "summary": pick_i18n(res.get("summary", {}), lang),
            "priority": res.get("priority", 0),
        })
    matches.sort(key=lambda x: -x["priority"])
    seen_urls = set()
    unique = []
    for m in matches:
        if m["url"] in seen_urls:
            continue
        seen_urls.add(m["url"])
        unique.append(m)
    return unique[:limit]


def build_link_chips_block(
    items: List[Dict[str, Any]],
    lang: str = "zh-TW",
    title: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    lang = normalize_lang(lang)
    return {
        "type": "link_chips",
        "title": title or t("officialLinksTitle", lang),
        "items": items,
    }


def get_official_links_for_task(
    task_id: str,
    school_info: Dict[str, Any],
    lang: str = "zh-TW",
) -> List[Dict[str, Any]]:
    """Simplified list for roadmap task detail panel."""
    return resolve_resources_for_task(task_id, profile_with_location(school_info), lang)


def enrich_roadmap_with_official_links(
    roadmap_response: Dict[str, Any],
    school_info: Dict[str, Any],
    lang: str = "zh-TW",
) -> Dict[str, Any]:
    ctx = profile_with_location(school_info)
    for phase in roadmap_response.get("phases", []):
        for task in phase.get("tasks", []):
            items = resolve_resources_for_task(task["id"], ctx, lang)
            task["official_links"] = [
                {
                    "label": i["label"],
                    "url": i["url"],
                    "tier": i["tier"],
                    "summary": i.get("summary", ""),
                }
                for i in items
            ]
    return roadmap_response


def build_context_suggested_chips(task_id: Optional[str], lang: str) -> List[Dict[str, Any]]:
    """Composer chips above chat input — loaded from backend locale files."""
    lang = normalize_lang(lang)
    if not task_id:
        return []

    # Try task-specific key first, then fall back to generic
    key = f"chipSuggestions_{task_id}"
    raw = t(key, lang)
    if raw == key:
        # key not found — use generic fallback
        raw = t("chipSuggestionsDefault", lang)
    if not raw or raw in (key, "chipSuggestionsDefault"):
        return []
    texts = [s.strip() for s in raw.split("||") if s.strip()]
    return [{"label": txt, "action": "send_message", "payload": txt} for txt in texts]
