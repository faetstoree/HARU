# -*- coding: utf-8 -*-
"""AI-powered quiz diagnosis synthesis."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from google.genai import types

from gemini_engine import generate_with_model_fallback
from quiz_engine import load_quiz_bank, normalize_lang, pick_i18n
from roadmap_engine import build_roadmap_response, pick_i18n as roadmap_pick_i18n, profile_from_dict

_DIAG_HEADER = {
    "zh-TW": "## \u8a3a\u65b7\u7d50\u679c\n\n\u6839\u64da\u4f60\u7684\u56de\u7b54\uff0cHaru \u6574\u7406\u4e86\u4ee5\u4e0b\u5efa\u8b70\uff1a",
    "en": "## Diagnosis\n\nBased on your answers, Haru recommends:",
    "ja": "## \u8a3a\u65ad\u7d50\u679c\n\n\u56de\u7b54\u306b\u57fa\u3065\u304f\u30a2\u30c9\u30d0\u30a4\u30b9\u3067\u3059\uff1a",
}
_DIAG_DEFAULT = {
    "zh-TW": "\u4f60\u7684\u9032\u5ea6\u8207\u8def\u7dda\u5716\u4e00\u81f4\uff0c\u8acb\u7e7c\u7e8c\u76ee\u524d\u7684\u91cd\u9ede\u4efb\u52d9\u3002",
    "en": "Your progress aligns with the roadmap. Continue your current focus task.",
    "ja": "\u30ed\u30fc\u30c9\u30de\u30c3\u30d7\u3068\u4e00\u81f4\u3057\u3066\u3044\u307e\u3059\u3002\u4eca\u306e\u30bf\u30b9\u30af\u3092\u7d9a\u3051\u3066\u304f\u3060\u3055\u3044\u3002",
}
_DIAG_PRIORITY = {
    "zh-TW": "\n\n**\u5efa\u8b70\u512a\u5148\u8655\u7406\uff1a**",
    "en": "\n\n**Suggested priorities:**",
    "ja": "\n\n**\u512a\u5148\u30bf\u30b9\u30af\uff1a**",
}
_CHIP_LABEL = {
    "zh-TW": "\u67e5\u770b\u4efb\u52d9",
    "en": "View task",
    "ja": "\u30bf\u30b9\u30af\u3092\u898b\u308b",
}


def _task_title_by_id(task_id: str, roadmap_data: Dict[str, Any], lang: str) -> str:
    for phase in roadmap_data.get("phases", []):
        for task in phase.get("tasks", []):
            if task.get("id") == task_id:
                return roadmap_pick_i18n(task.get("title", {}), lang)
    for t in roadmap_data.get("next_tasks", []):
        if t.get("id") == task_id:
            return t.get("title", task_id)
    return task_id


def _collect_quiz_context(
    quiz_state: Dict[str, Any],
    school_info: Dict[str, Any],
    completed_tasks: List[str],
    lang: str,
) -> Dict[str, Any]:
    lang = normalize_lang(lang)
    bank = {q["id"]: q for q in load_quiz_bank().get("questions", [])}
    answers_detail: List[Dict[str, str]] = []
    recommendations: List[str] = []
    suggested_task_ids: List[str] = []

    for ans in quiz_state.get("answers", []):
        q = bank.get(ans.get("question_id", ""))
        if not q:
            continue
        choice = next((c for c in q.get("choices", []) if c["id"] == ans.get("choice_id")), None)
        if not choice:
            continue
        prompt = pick_i18n(q.get("prompt", {}), lang)
        label = pick_i18n(choice.get("label", {}), lang)
        answers_detail.append({"question": prompt, "answer": label})
        if choice.get("recommendation"):
            recommendations.append(pick_i18n(choice["recommendation"], lang))
        if choice.get("suggest_task"):
            suggested_task_ids.append(choice["suggest_task"])

    profile = profile_from_dict(school_info)
    roadmap_data = build_roadmap_response(profile, completed_tasks, lang)
    focus_id = quiz_state.get("focus_task_id")
    suggested_task_ids = list(dict.fromkeys(suggested_task_ids))
    if focus_id and focus_id not in suggested_task_ids:
        suggested_task_ids.insert(0, focus_id)

    task_titles = [
        _task_title_by_id(tid, roadmap_data, lang) for tid in suggested_task_ids[:4]
    ]

    return {
        "lang": lang,
        "answers_detail": answers_detail,
        "recommendations": recommendations,
        "suggested_task_ids": suggested_task_ids,
        "task_titles": task_titles,
        "roadmap_data": roadmap_data,
        "focus_id": focus_id,
    }


def build_rule_based_diagnosis(ctx: Dict[str, Any]) -> Dict[str, Any]:
    lang = ctx["lang"]
    lines = [pick_i18n(_DIAG_HEADER, lang)]
    if ctx["recommendations"]:
        for i, rec in enumerate(ctx["recommendations"][:6], 1):
            lines.append(f"{i}. {rec}")
    else:
        lines.append(pick_i18n(_DIAG_DEFAULT, lang))

    if ctx["task_titles"]:
        lines.append(pick_i18n(_DIAG_PRIORITY, lang))
        for title in ctx["task_titles"]:
            lines.append(f"- {title}")

    blocks: List[Dict[str, Any]] = [{"type": "text", "content": "\n".join(lines)}]
    chips = []
    chip_label = _CHIP_LABEL.get(lang, _CHIP_LABEL["en"])
    for tid in ctx["suggested_task_ids"][:3]:
        chips.append({"label": chip_label, "action": "open_task", "payload": tid})
    if chips:
        blocks.append({"type": "chips", "items": chips})

    return {
        "message_blocks": blocks,
        "suggested_task_ids": ctx["suggested_task_ids"],
        "ai_generated": False,
        "source": "rule_engine",
    }


async def synthesize_quiz_diagnosis(
    quiz_state: Dict[str, Any],
    school_info: Dict[str, Any],
    completed_tasks: List[str],
    lang: str,
    *,
    genai_client: Any = None,
    target_lang_name: str = "Japanese",
) -> Dict[str, Any]:
    ctx = _collect_quiz_context(quiz_state, school_info, completed_tasks, lang)
    if not genai_client:
        return build_rule_based_diagnosis(ctx)

    qa_lines = "\n".join(
        f"- Q: {a['question']}\n  A: {a['answer']}" for a in ctx["answers_detail"]
    ) or "No answers recorded."
    next_tasks = ctx["roadmap_data"].get("next_tasks") or []
    next_summary = "\n".join(f"- {t['id']}: {t['title']}" for t in next_tasks[:5])

    prompt = f"""You are Haru, an AI mentor for international students in Japan.
Write a personalized diagnosis after a multiple-choice quiz session.

[Student profile]
- School: {school_info.get('school_name')}
- Area: {school_info.get('location')}
- Housing: {school_info.get('housing_type')}
- Japanese level: {school_info.get('japanese_level')}

[Roadmap next tasks]
{next_summary or 'All major tasks done.'}

[Quiz Q&A]
{qa_lines}

[Rule-based hints from choices]
{chr(10).join(ctx['recommendations']) or 'None'}

Write in {target_lang_name} only:
1. A short empathetic summary (2-3 sentences) of their situation
2. Numbered action steps (3-5) tailored to their answers
3. One sentence on what to do today first

Plain text only. No URLs. Use markdown headings (##) sparingly."""

    try:
        response, _model, _used = await generate_with_model_fallback(
            genai_client,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(
                system_instruction="You are Haru. Be concise, practical, and encouraging.",
            ),
        )
        text = (response.text or "").strip()
        if not text:
            return build_rule_based_diagnosis(ctx)

        blocks: List[Dict[str, Any]] = [{"type": "text", "content": text}]
        chips = []
        chip_label = _CHIP_LABEL.get(ctx["lang"], _CHIP_LABEL["en"])
        for tid in ctx["suggested_task_ids"][:3]:
            chips.append({
                "label": chip_label,
                "action": "open_task",
                "payload": tid,
            })
        if chips:
            blocks.append({"type": "chips", "items": chips})

        return {
            "message_blocks": blocks,
            "suggested_task_ids": ctx["suggested_task_ids"],
            "ai_generated": True,
            "source": "llm",
        }
    except Exception:
        return build_rule_based_diagnosis(ctx)
