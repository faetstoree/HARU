"""AI-generated personalized action plan content for PDF export."""
from __future__ import annotations

import re
from typing import Any, Dict, List

from google.genai import types

from gemini_engine import generate_with_model_fallback
from roadmap_engine import normalize_lang


def _parse_sections(text: str) -> Dict[str, str]:
    sections: Dict[str, str] = {}
    current = "_body"
    buf: List[str] = []
    for line in (text or "").splitlines():
        header = re.match(r"^#{1,3}\s*(.+)$", line.strip())
        if header:
            if buf:
                sections[current] = "\n".join(buf).strip()
            current = header.group(1).strip().lower()
            buf = []
        else:
            buf.append(line)
    if buf:
        sections[current] = "\n".join(buf).strip()
    return sections


def _parse_numbered_steps(text: str) -> List[str]:
    steps: List[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        m = re.match(r"^\s*(\d+)[\.\)]\s+(.+)$", stripped)
        if m:
            step = m.group(2).strip()
            if step:
                steps.append(step)
            continue
        m2 = re.match(r"^\s*[-*]\s+(.+)$", stripped)
        if m2:
            steps.append(m2.group(1).strip())
    return steps


def build_action_plan_ai_prompt(
    plan: Dict[str, Any],
    roadmap_data: Dict[str, Any],
    school_info: Dict[str, Any],
    lang: str,
    current_address: str = "",
) -> str:
    lang = normalize_lang(lang)
    target = {"zh-TW": "Traditional Chinese", "en": "English", "ja": "Japanese"}.get(lang, "English")
    focus = plan.get("focus") or {}
    next_lines = "\n".join(
        f"- {t.get('title', '')}: {(t.get('summary') or '')[:80]}"
        for t in (plan.get("upcoming") or [])[:3]
    )
    completed = ", ".join(plan.get("completed_milestones") or []) or "none"

    return f"""You are Haru, an AI mentor for international students in Japan.
Write a personalized action plan for THIS student only. Use Google Search when helpful for
local office hours, nearest facilities, or current procedures in their area.

Reply in {target} only. Use this exact markdown structure:

## Greeting
(2-3 warm sentences addressing them by situation - school, area, progress)

## Priority
(1 short paragraph: what matters most RIGHT NOW and why)

## Steps
1. (specific actionable step)
2. (next step)
3. (continue 4-7 steps total)

## Encouragement
(1 supportive closing sentence)

Do NOT include URLs or markdown links.

STUDENT:
- School: {school_info.get('school_name', 'N/A')}
- Area: {school_info.get('location', 'N/A')}
- GPS / address hint: {current_address or 'N/A'}
- Arrival: {school_info.get('arrival_date', 'N/A')}
- Japanese: {school_info.get('japanese_level', 'N/A')}
- Progress: {roadmap_data.get('progress', {}).get('completed', 0)}/{roadmap_data.get('progress', {}).get('total', 0)}
- Route: {plan.get('route_label', '')}
- Completed recently: {completed}

CURRENT FOCUS TASK:
- Title: {focus.get('title', 'All major steps done')}
- Summary: {focus.get('summary', '')}
- Documents: {', '.join(focus.get('documents') or []) or 'N/A'}

UPCOMING AFTER THIS:
{next_lines or 'N/A'}
"""


async def enrich_action_plan_with_ai(
    plan: Dict[str, Any],
    roadmap_data: Dict[str, Any],
    school_info: Dict[str, Any],
    lang: str,
    current_address: str,
    genai_client,
) -> Dict[str, Any]:
    """Replace template copy with AI-personalized narrative and steps."""
    if plan.get("all_done"):
        return plan

    prompt = build_action_plan_ai_prompt(
        plan, roadmap_data, school_info, lang, current_address
    )
    response, model, tools_used = await generate_with_model_fallback(
        genai_client,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            max_output_tokens=1200,
        ),
    )
    raw = (response.text or "").strip()
    sections = _parse_sections(raw)

    greeting = (
        sections.get("greeting")
        or sections.get("_body", "").split("\n\n")[0]
        or plan.get("greeting", "")
    )
    priority = sections.get("priority") or ""
    steps_text = sections.get("steps") or ""
    steps = _parse_numbered_steps(steps_text) or _parse_numbered_steps(raw)
    encouragement = sections.get("encouragement") or ""

    agent_message = priority
    if encouragement:
        agent_message = f"{agent_message}\n\n{encouragement}".strip()

    if steps:
        plan["steps"] = steps
    if greeting:
        plan["greeting"] = greeting
    if agent_message:
        plan["agent_message"] = agent_message

    plan["ai_generated"] = True
    plan["ai_model"] = model
    plan["ai_used_search"] = tools_used
    return plan
