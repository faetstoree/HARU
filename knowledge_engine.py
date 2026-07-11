"""Structured knowledge DB: articles, trusted sources, interactive service guides."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

from roadmap_engine import normalize_lang, pick_i18n
from task_id_aliases import task_ids_overlap
from backend_i18n import t

KB_DIR = os.path.join(os.path.dirname(__file__), "data", "knowledge")


@lru_cache(maxsize=1)
def load_sources() -> Dict[str, Any]:
    with open(os.path.join(KB_DIR, "sources.json"), "r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_articles() -> Dict[str, Any]:
    with open(os.path.join(KB_DIR, "articles.json"), "r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_guides() -> Dict[str, Any]:
    with open(os.path.join(KB_DIR, "service_guides.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def _source_by_id() -> Dict[str, Dict[str, Any]]:
    return {s["id"]: s for s in load_sources().get("sources", [])}


def resolve_sources(source_ids: List[str], lang: str) -> List[Dict[str, Any]]:
    lang = normalize_lang(lang)
    by_id = _source_by_id()
    out = []
    for sid in source_ids:
        src = by_id.get(sid)
        if not src:
            continue
        out.append({
            "source_id": sid,
            "label": pick_i18n(src.get("name", {}), lang),
            "url": src.get("url", ""),
            "tier": src.get("tier", "official"),
            "domain": src.get("domain", ""),
            "trust_score": src.get("trust_score", 0),
        })
    return out


def resolve_articles_for_task(task_id: str, lang: str, limit: int = 2) -> List[Dict[str, Any]]:
    lang = normalize_lang(lang)
    matches = []
    for art in load_articles().get("articles", []):
        if not task_ids_overlap(task_id, art.get("task_ids") or []):
            continue
        sections = []
        for sec in art.get("sections") or []:
            sections.append({
                "heading": pick_i18n(sec.get("heading", {}), lang),
                "body": pick_i18n(sec.get("body", {}), lang),
                "sources": resolve_sources(sec.get("source_ids") or [], lang),
            })
        matches.append({
            "id": art["id"],
            "title": pick_i18n(art.get("title", {}), lang),
            "summary": pick_i18n(art.get("summary", {}), lang),
            "sections": sections,
            "sources": resolve_sources(art.get("source_ids") or [], lang),
            "priority": art.get("priority", 0),
        })
    matches.sort(key=lambda x: -x["priority"])
    return matches[:limit]


def resolve_guides_for_task(task_id: str, lang: str, limit: int = 2) -> List[Dict[str, Any]]:
    lang = normalize_lang(lang)
    matches = []
    for g in load_guides().get("guides", []):
        if not task_ids_overlap(task_id, g.get("task_ids") or []):
            continue
        matches.append({
            "id": g["id"],
            "title": pick_i18n(g.get("title", {}), lang),
            "description": pick_i18n(g.get("description", {}), lang),
            "step_count": len(g.get("steps") or []),
            "estimated_min": g.get("estimated_min"),
            "service_key": g.get("service_key", ""),
            "priority": g.get("priority", 0),
        })
    matches.sort(key=lambda x: -x["priority"])
    return matches[:limit]


def get_guide(guide_id: str, lang: str) -> Optional[Dict[str, Any]]:
    lang = normalize_lang(lang)
    for g in load_guides().get("guides", []):
        if g["id"] != guide_id:
            continue
        steps_out = []
        for i, step in enumerate(g.get("steps") or [], 1):
            checklist = []
            for item in step.get("checklist") or []:
                checklist.append({"text": pick_i18n(item.get("text", {}), lang), "checked": False})
            tip = step.get("tip") or {}
            steps_out.append({
                "index": i,
                "title": pick_i18n(step.get("title", {}), lang),
                "instruction": pick_i18n(step.get("instruction", {}), lang),
                "checklist": checklist,
                "tip": pick_i18n(tip, lang) if tip else "",
                "external_url": step.get("external_url") or "",
            })
        return {
            "id": g["id"],
            "title": pick_i18n(g.get("title", {}), lang),
            "description": pick_i18n(g.get("description", {}), lang),
            "estimated_min": g.get("estimated_min"),
            "task_ids": g.get("task_ids", []),
            "steps": steps_out,
            "sources": resolve_sources(g.get("source_ids") or [], lang),
        }
    return None


def build_kb_context_for_llm(task_id: str, lang: str, max_chars: int = 2000) -> str:
    """Trusted facts only — injected into LLM context; URLs from DB."""
    lang = normalize_lang(lang)
    articles = resolve_articles_for_task(task_id, lang, limit=1)
    guides = resolve_guides_for_task(task_id, lang, limit=1)
    parts = ["[Trusted knowledge base — cite only these facts and URLs, do not invent links]"]
    if articles:
        a = articles[0]
        parts.append(f"Topic: {a['title']}")
        parts.append(a["summary"])
        for sec in a.get("sections", [])[:2]:
            parts.append(f"- {sec['heading']}: {sec['body']}")
        for s in a.get("sources", [])[:3]:
            parts.append(f"  Source: {s['label']} | {s['url']}")
    if guides:
        g = guides[0]
        parts.append(f"Interactive guide available: {g['title']} ({g['step_count']} steps)")
    text = "\n".join(parts)
    return text[:max_chars]


def build_kb_snippet_block(article: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "kb_snippet",
        "article_id": article["id"],
        "title": article["title"],
        "content": article["summary"],
        "sources": article.get("sources", []),
    }


def build_guide_card_block(guide: Dict[str, Any], lang: str) -> Dict[str, Any]:
    lang = normalize_lang(lang)
    return {
        "type": "guide_card",
        "guide_id": guide["id"],
        "title": guide["title"],
        "description": guide.get("description", ""),
        "step_count": guide.get("step_count", 0),
        "estimated_min": guide.get("estimated_min"),
        "cta_label": t("guideStartWalkthrough", lang),
    }


def build_source_citations_block(sources: List[Dict[str, Any]], lang: str) -> Dict[str, Any]:
    lang = normalize_lang(lang)
    return {
        "type": "source_citations",
        "title": t("sourceCitationsTitle", lang),
        "items": sources,
    }


def build_knowledge_blocks_for_task(task_id: str, lang: str) -> List[Dict[str, Any]]:
    """Deterministic blocks from KB for chat / task UI."""
    blocks: List[Dict[str, Any]] = []
    articles = resolve_articles_for_task(task_id, lang, limit=1)
    guides = resolve_guides_for_task(task_id, lang, limit=1)
    all_source_ids: List[str] = []

    if articles:
        blocks.append(build_kb_snippet_block(articles[0]))
        for s in articles[0].get("sources", []):
            if s["source_id"] not in all_source_ids:
                all_source_ids.append(s["source_id"])

    if guides:
        blocks.append(build_guide_card_block(guides[0], lang))

    if all_source_ids:
        sources = resolve_sources(all_source_ids, lang)
        if sources:
            blocks.append(build_source_citations_block(sources, lang))

    return blocks


def get_knowledge_bundle_for_task(task_id: str, lang: str) -> Dict[str, Any]:
    articles = resolve_articles_for_task(task_id, lang, limit=3)
    guides = resolve_guides_for_task(task_id, lang, limit=3)
    source_ids: List[str] = []
    for a in articles:
        for s in a.get("sources", []):
            if s["source_id"] not in source_ids:
                source_ids.append(s["source_id"])
    return {
        "task_id": task_id,
        "articles": articles,
        "guides": guides,
        "sources": resolve_sources(source_ids, lang),
    }
