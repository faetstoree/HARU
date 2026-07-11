"""AI-powered personalized roadmap generation.

On first onboarding, Gemini reads the student's full profile and generates:
  - A personalized greeting / mission statement
  - Per-task overrides: personalized summary, step list, tips
  - An overall goal narrative for the home screen agent card

The output is stored in the User.ai_roadmap column (JSON) and merged with
the static roadmap on every subsequent request.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from google.genai import types

from gemini_engine import generate_with_model_fallback
from roadmap_engine import (
    build_roadmap_response,
    normalize_lang,
    pick_i18n,
    profile_from_dict,
)

# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

_TARGET_LANG = {
    "zh-TW": "Traditional Chinese (繁體中文)",
    "en": "English",
    "ja": "Japanese (日本語)",
}


def _build_task_list_summary(roadmap_data: Dict[str, Any], lang: str) -> str:
    lines: List[str] = []
    for phase in roadmap_data.get("phases", []):
        phase_title = phase.get("title", phase.get("id", ""))
        for task in phase.get("tasks", []):
            if task.get("state") == "skipped":
                continue
            lines.append(
                f'  [{phase_title}] {task["id"]}: {task["title"]} — {(task.get("summary") or "")[:80]}'
            )
    return "\n".join(lines) or "No tasks found."


def build_ai_roadmap_prompt(
    school_info: Dict[str, Any],
    completed_tasks: List[str],
    roadmap_data: Dict[str, Any],
    lang: str,
) -> str:
    lang = normalize_lang(lang)
    target_lang = _TARGET_LANG.get(lang, "English")
    profile = profile_from_dict(school_info)
    task_list = _build_task_list_summary(roadmap_data, lang)
    next_tasks = roadmap_data.get("next_tasks", [])
    focus = next_tasks[0] if next_tasks else {}
    progress = roadmap_data.get("progress", {})

    school_type_labels = {
        "language_school": "language school (語学学校)",
        "university": "university (大学)",
        "vocational": "vocational school (専門学校)",
        "high_school": "high school (高校)",
    }
    housing_labels = {
        "dorm": "school dormitory",
        "rental": "self-arranged rental apartment",
        "housing_tbd": "housing not yet decided",
    }

    return f"""You are Haru, an AI mentor for international students newly arrived in Japan.

A student just completed onboarding. Based on their profile, generate a FULLY PERSONALIZED roadmap overlay.

Respond ONLY in valid JSON matching this exact schema (no markdown fences, no extra keys):
{{
  "mission": "<2-3 sentence personal mission statement for this student — warm, specific to their school/location/situation>",
  "agent_greeting": "<1 sentence warm greeting Haru says on the home screen, mentioning their name/school if available>",
  "goal_summary": "<1 paragraph: what success looks like for this student after completing all tasks>",
  "task_overrides": [
    {{
      "task_id": "<exact task_id from the list below>",
      "personalized_summary": "<2-3 sentences: why this task matters for THIS student specifically, referencing their school/area/situation>",
      "steps": ["<specific actionable step 1>", "<step 2>", "<step 3 — max 5 steps>"],
      "tips": ["<tip specific to their profile — e.g. language level, housing type, school type>"]
    }}
  ],
  "priority_message": "<1 short paragraph about the single most important thing to do first and why, given their arrival date and current progress>"
}}

Rules:
- Write ONLY in {target_lang}.
- task_overrides MUST cover ALL tasks in the task list below (one entry per task_id).
- steps should be concrete and reference their location ({school_info.get('location', 'Japan')}) where relevant.
- tips should reflect their specific situation (Japanese level: {school_info.get('japanese_level', 'unknown')}, housing: {housing_labels.get(profile.get('housing_type', 'dorm'), 'dorm')}).
- Do NOT include URLs or markdown links in any field.
- Keep steps under 20 words each. Keep personalized_summary under 60 words.

STUDENT PROFILE:
- School: {school_info.get('school_name', 'N/A')}
- School type: {school_type_labels.get(profile.get('school_type', 'language_school'), profile.get('school_type', ''))}
- Area / City: {school_info.get('location', 'N/A')}
- Arrival date: {school_info.get('arrival_date', 'N/A')}
- Japanese level: {school_info.get('japanese_level', 'N/A')}
- Housing: {housing_labels.get(profile.get('housing_type', 'dorm'), 'dorm')}
- Part-time work plan: {profile.get('part_time_plan', 'no')}
- Got residence card at airport: {school_info.get('has_residence_card', True)}
- Already bought SIM at airport: {profile.get('sim_at_airport', False)}
- Already exchanged currency: {profile.get('already_exchanged', False)}
- Progress: {progress.get('completed', 0)}/{progress.get('total', 0)} tasks done
- Current focus task: {focus.get('title', 'N/A')} ({focus.get('id', '')})

TASK LIST (generate one task_override per task_id):
{task_list}
"""


# ---------------------------------------------------------------------------
# AI generation
# ---------------------------------------------------------------------------

async def generate_ai_roadmap(
    school_info: Dict[str, Any],
    completed_tasks: List[str],
    lang: str,
    genai_client: Any,
) -> Optional[Dict[str, Any]]:
    """Call Gemini to generate a personalized roadmap overlay.

    Returns the parsed JSON dict, or None on failure.
    """
    lang = normalize_lang(lang)
    profile = profile_from_dict(school_info)
    roadmap_data = build_roadmap_response(profile, completed_tasks, lang)

    prompt = build_ai_roadmap_prompt(school_info, completed_tasks, roadmap_data, lang)

    try:
        response, model, _ = await generate_with_model_fallback(
            genai_client,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are Haru. Output ONLY valid JSON — no markdown, no prose outside JSON. "
                    "Be warm, practical, and specific to the student's situation."
                ),
                max_output_tokens=4096,
                # No Google Search here — pure generation from profile facts
            ),
        )
        raw = (response.text or "").strip()

        # Strip markdown code fences if model wrapped output anyway
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        parsed = json.loads(raw)

        # Validate required top-level keys
        required = {"mission", "agent_greeting", "goal_summary", "task_overrides", "priority_message"}
        if not required.issubset(parsed.keys()):
            missing = required - parsed.keys()
            print(f"[roadmap_ai_engine] Missing keys in AI response: {missing}")
            return None

        # Validate task_overrides entries
        valid_overrides = []
        for ov in parsed.get("task_overrides", []):
            if not isinstance(ov, dict) or not ov.get("task_id"):
                continue
            valid_overrides.append({
                "task_id": ov["task_id"],
                "personalized_summary": (ov.get("personalized_summary") or "").strip(),
                "steps": [s for s in (ov.get("steps") or []) if isinstance(s, str) and s.strip()],
                "tips": [t for t in (ov.get("tips") or []) if isinstance(t, str) and t.strip()],
            })
        parsed["task_overrides"] = valid_overrides
        parsed["_model"] = model
        parsed["_lang"] = lang

        return parsed

    except json.JSONDecodeError as exc:
        print(f"[roadmap_ai_engine] JSON parse error: {exc}")
        return None
    except Exception as exc:
        print(f"[roadmap_ai_engine] Generation failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# Merging AI overlay into static roadmap response
# ---------------------------------------------------------------------------

def merge_ai_overlay_into_roadmap(
    roadmap_data: Dict[str, Any],
    ai_overlay: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Merge AI-generated personalizations into a static roadmap_response dict.

    The static roadmap structure is kept intact (phases, progress, graph, etc.).
    AI content is overlaid on matching task summaries, tips, and a top-level
    'ai_personalization' key is added for the frontend to display.
    """
    if not ai_overlay:
        return roadmap_data

    # Build a fast lookup: task_id -> override
    overrides: Dict[str, Dict[str, Any]] = {
        ov["task_id"]: ov
        for ov in ai_overlay.get("task_overrides", [])
    }

    # Overlay task summaries and tips inside phases
    for phase in roadmap_data.get("phases", []):
        for task in phase.get("tasks", []):
            tid = task.get("id")
            if tid not in overrides:
                continue
            ov = overrides[tid]
            if ov.get("personalized_summary"):
                task["summary"] = ov["personalized_summary"]
            if ov.get("tips"):
                task["tips"] = ov["tips"]
            if ov.get("steps"):
                task["ai_steps"] = ov["steps"]

    # Overlay next_tasks summaries
    for task in roadmap_data.get("next_tasks", []):
        tid = task.get("id")
        if tid in overrides and overrides[tid].get("personalized_summary"):
            task["summary"] = overrides[tid]["personalized_summary"]

    # Add top-level AI personalization block for home screen / agent card
    roadmap_data["ai_personalization"] = {
        "mission": ai_overlay.get("mission", ""),
        "agent_greeting": ai_overlay.get("agent_greeting", ""),
        "goal_summary": ai_overlay.get("goal_summary", ""),
        "priority_message": ai_overlay.get("priority_message", ""),
        "model": ai_overlay.get("_model", ""),
        "lang": ai_overlay.get("_lang", ""),
    }

    return roadmap_data
