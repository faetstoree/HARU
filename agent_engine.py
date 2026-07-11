"""Rule-based agent decisions from roadmap data (no LLM)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from roadmap_engine import normalize_lang, pick_i18n
from backend_i18n import t

NAVIGATION_TASK_IDS = {
    "task_ward_office",
    "task_resident_reg_complete",
    "task_bank",
    "task_phone",
    "task_mynumber_notice",
    "task_pension_student",
    "task_move_in",
    "task_housing_rental_managed",
    "task_housing_rental_self",
}


def _navigation_query(task_id: str, school_info: Dict[str, Any], current_address: str, lang: str) -> str:
    loc = school_info.get("location") or current_address or ""
    if task_id in ("task_ward_office", "task_resident_reg_complete", "task_mynumber_notice", "task_pension_student"):
        return t("navWardOffice", lang, loc=loc)
    if task_id == "task_bank":
        return t("navBank", lang, loc=loc)
    if task_id == "task_phone":
        return t("navPhone", lang, loc=loc)
    return loc


def build_rule_based_decision(
    roadmap_data: Dict[str, Any],
    school_info: Dict[str, Any],
    lang: str = "zh-TW",
    current_address: str = "",
    problem_report: Optional[str] = None,
    task_action: Optional[str] = None,
) -> Dict[str, Any]:
    """Build agent UI payload from roadmap engine output without calling an LLM."""
    lang = normalize_lang(lang)
    next_tasks: List[Dict[str, Any]] = roadmap_data.get("next_tasks") or []

    if not next_tasks:
        return {
            "expression": "success",
            "current_focus_title": t("allDone", lang),
            "narrative": t("completedNarrative", lang),
            "action_type": "none",
            "action_label": "",
            "action_data": "",
            "upcoming_hint": "",
            "newly_completed_tasks": [],
            "source": "rule_engine",
        }

    focus = next_tasks[0]
    tips = focus.get("tips") or []
    narrative = focus.get("summary") or ""
    if tips:
        narrative = narrative + "\n\n" + "\n".join(f"• {tip}" for tip in tips[:4])

    if task_action == "completed":
        narrative = t(
            "markedCompleteNext", lang,
            title=focus["title"],
            summary=focus.get("summary", ""),
        )

    action_type = "none"
    action_data = ""
    action_label = ""
    task_id = focus.get("id", "")

    if task_id in NAVIGATION_TASK_IDS:
        action_type = "navigation"
        action_data = _navigation_query(task_id, school_info, current_address, lang)
        action_label = t("navActionLabel", lang)

    upcoming = next_tasks[1]["title"] if len(next_tasks) > 1 else ""

    return {
        "expression": "guiding",
        "current_focus_title": focus.get("title", ""),
        "narrative": narrative,
        "action_type": action_type,
        "action_label": action_label,
        "action_data": action_data,
        "upcoming_hint": upcoming,
        "newly_completed_tasks": [],
        "source": "rule_engine",
    }


def should_use_llm_for_agent(
    problem_report: Optional[str] = None,
    task_action: Optional[str] = None,
    force_llm: bool = False,
) -> bool:
    """Use LLM for agent decisions. Always true — AI is the default behaviour.

    The rule-based fallback is used only when called with force_llm=False AND
    problem_report is None AND task_action is None, which now only happens in
    internal/background contexts where latency matters. The home screen always
    passes force_llm=True so the student gets a real AI response.
    """
    # Always prefer AI when possible
    return True
