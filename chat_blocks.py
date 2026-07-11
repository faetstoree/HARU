"""Build structured chat message blocks (merge LLM text + official DB + roadmap)."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from resource_engine import (
    build_context_suggested_chips,
    build_link_chips_block,
    profile_with_location,
    resolve_resources_for_task,
)
from knowledge_engine import build_knowledge_blocks_for_task
from roadmap_engine import get_next_tasks
from backend_i18n import t


def _text_block(content: str) -> Dict[str, Any]:
    return {"type": "text", "content": content}


def _action_chips_for_task(
    task_id: str,
    lang: str,
    school_info: Optional[Dict[str, Any]] = None,
    maps_query: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    items = [
        {"label": t("chipComplete", lang), "action": "complete_task", "payload": task_id},
        {"label": t("chipTask", lang), "action": "open_task", "payload": task_id},
    ]
    query = (maps_query or (school_info or {}).get("location") or "").strip()
    if query:
        items.append({"label": t("chipMaps", lang), "action": "open_maps", "payload": query})
    return {
        "type": "chips",
        "items": items,
    }


def merge_chat_blocks(
    text_content: str,
    school_info: Dict[str, Any],
    completed_tasks: List[str],
    lang: str,
    focus_task_id: Optional[str] = None,
    current_address: Optional[str] = None,
    extra_blocks: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Merge LLM narrative with deterministic blocks."""
    profile = profile_with_location(school_info)
    lang_key = lang if lang in ("zh-TW", "en", "ja") else "en"

    if not focus_task_id:
        next_tasks = get_next_tasks(profile, completed_tasks, limit=1, lang=lang_key)
        focus_task_id = next_tasks[0]["id"] if next_tasks else None

    blocks: List[Dict[str, Any]] = []
    if text_content and text_content.strip():
        blocks.append(_text_block(text_content.strip()))

    for block in extra_blocks or []:
        if block and block.get("type"):
            blocks.append(block)

    if focus_task_id:
        # Knowledge DB blocks first (structured facts + walkthrough card + citations)
        kb_blocks = build_knowledge_blocks_for_task(focus_task_id, lang_key)
        blocks.extend(kb_blocks)

        links = resolve_resources_for_task(focus_task_id, profile, lang_key, limit=4)
        if links:
            blocks.append(build_link_chips_block(links, lang_key))

        maps_query = (current_address or school_info.get("location") or "").strip()
        chips = _action_chips_for_task(
            focus_task_id, lang_key, school_info, maps_query=maps_query
        )
        if chips:
            blocks.append(chips)

    if not blocks:
        blocks.append(_text_block(""))

    suggested = build_context_suggested_chips(focus_task_id, lang_key)
    return {
        "role": "model",
        "blocks": blocks,
        "focus_task_id": focus_task_id,
        "suggested_chips": suggested,
    }


def parse_llm_text_or_json(raw: str) -> str:
    """Extract plain text from LLM response (ignore accidental JSON wrappers)."""
    raw = (raw or "").strip()
    if raw.startswith("{"):
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict) and "blocks" in obj:
                for b in obj["blocks"]:
                    if b.get("type") == "text":
                        return b.get("content", raw)
            if isinstance(obj, dict) and "content" in obj:
                return obj["content"]
        except json.JSONDecodeError:
            pass
    return raw


def message_to_history_text(msg: Dict[str, Any]) -> str:
    """Flatten blocks to text for LLM context in history."""
    if msg.get("text"):
        return msg["text"]
    parts = []
    for b in msg.get("blocks") or []:
        if b.get("type") == "text":
            parts.append(b.get("content", ""))
        elif b.get("type") == "images":
            n = len(b.get("items") or [])
            if n:
                parts.append(f"[{n} image(s) attached]")
        elif b.get("type") == "mermaid":
            title = b.get("title") or "diagram"
            parts.append(f"[{title}]")
    return "\n".join(parts).strip()
