"""Task detail expansion and AI-personalized roadmaps."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from knowledge_engine import build_kb_context_for_llm, resolve_articles_for_task
from roadmap_branch_engine import get_branch_point_for_task, load_branches
from roadmap_engine import load_roadmap, normalize_lang, pick_i18n, profile_from_dict
from backend_i18n import t


def _task_raw(task_id: str) -> Optional[Dict[str, Any]]:
    roadmap = load_roadmap()
    for t in roadmap["tasks"]:
        if t["id"] == task_id:
            return t
    for t in load_branches().get("supplemental_tasks") or []:
        if t["id"] == task_id:
            return t
    return None


def get_static_task_expansion(
    task_id: str,
    school_info: Dict[str, Any],
    branch_choices: Dict[str, str],
    lang: str = "zh-TW",
) -> Dict[str, Any]:
    """Rich static expansion: articles, steps outline, branch context."""
    lang = normalize_lang(lang)
    profile = profile_from_dict(school_info)
    task = _task_raw(task_id)
    if not task:
        return {"sections": [], "branch_point": None}

    sections: List[Dict[str, Any]] = []

    articles = resolve_articles_for_task(task_id, lang, limit=2)
    for art in articles:
        for sec in art.get("sections") or []:
            sections.append({
                "heading": sec.get("heading", ""),
                "body": sec.get("body", ""),
                "sources": sec.get("sources") or [],
            })

    overview = pick_i18n(task.get("summary"), lang)
    if overview:
        sections.insert(0, {
            "heading": t("sectionOverview", lang),
            "body": overview,
            "sources": [],
        })

    tips = task.get("tips") or []
    if tips:
        tip_lines = "\n".join(f"• {pick_i18n(tip, lang)}" for tip in tips)
        sections.append({
            "heading": t("sectionTips", lang),
            "body": tip_lines,
            "sources": [],
        })

    docs = task.get("documents") or []
    if docs:
        doc_lines = "\n".join(
            f"• {pick_i18n(d.get('label'), lang) if isinstance(d.get('label'), dict) else d.get('label', '')}"
            for d in docs
        )
        sections.append({
            "heading": t("sectionDocuments", lang),
            "body": doc_lines,
            "sources": [],
        })

    branch_point = get_branch_point_for_task(task_id, profile, branch_choices, lang)

    return {
        "task_id": task_id,
        "title": pick_i18n(task.get("title"), lang) if task else task_id,
        "sections": sections,
        "branch_point": branch_point,
    }


def build_personalize_prompt(
    task_id: str,
    school_info: Dict[str, Any],
    completed_tasks: List[str],
    branch_choices: Dict[str, str],
    lang: str,
    current_address: Optional[str] = None,
) -> str:
    lang = normalize_lang(lang)
    task = _task_raw(task_id)
    profile = profile_from_dict(school_info)
    kb = build_kb_context_for_llm(task_id, lang)

    branch_lines = []
    for bp in load_branches().get("branch_points") or []:
        cid = branch_choices.get(bp["id"])
        if not cid:
            continue
        choice = next((c for c in bp.get("choices") or [] if c["id"] == cid), None)
        if choice:
            branch_lines.append(f"- {pick_i18n(bp.get('prompt'), lang)} → {pick_i18n(choice.get('label'), lang)}")

    target_lang = {"zh-TW": "Traditional Chinese", "en": "English", "ja": "Japanese"}.get(lang, "English")

    return f"""Create a personalized step-by-step action plan for this relocation task.

Reply in {target_lang} only. Use numbered steps (1. 2. 3.). Be specific to the user's situation.
Do NOT include URLs or markdown links — the system adds official links separately.
Keep under 400 words.

USER PROFILE:
- School: {school_info.get('school_name', 'N/A')}
- Location: {school_info.get('location', 'N/A')}
- Current GPS address: {current_address or 'N/A'}
- Arrival date: {school_info.get('arrival_date', 'N/A')}
- Japanese level: {school_info.get('japanese_level', 'N/A')}
- Housing: {profile.get('housing_type')}
- Part-time plan: {profile.get('part_time_plan')}
- Completed tasks: {', '.join(completed_tasks) or 'none'}

BRANCH CHOICES:
{chr(10).join(branch_lines) if branch_lines else 'None yet'}

TASK: {pick_i18n(task.get('title'), lang) if task else task_id}
SUMMARY: {pick_i18n(task.get('summary'), lang) if task else ''}

TRUSTED KNOWLEDGE:
{kb or 'N/A'}

Include: what to prepare, where to go (use their area), estimated time, common mistakes for their profile."""


def build_mock_personalized_plan(
    task_id: str,
    school_info: Dict[str, Any],
    branch_choices: Dict[str, str],
    lang: str,
) -> str:
    lang = normalize_lang(lang)
    task = _task_raw(task_id)
    title = pick_i18n(task.get("title"), lang) if task else task_id
    loc = school_info.get("location") or t("mockDefaultLocation", lang)
    school = school_info.get("school_name") or t("mockDefaultSchool", lang)

    if lang == "ja":
        return (
            f"【Mock】{title} の個人プラン（{school}・{loc}向け）\n\n"
            f"1. {t('mockStep1Docs', lang)}\n"
            f"2. {t('mockStep2Hours', lang, loc=loc)}\n"
            f"3. {t('mockStep3Orientation', lang)}\n"
            f"4. {t('mockStep4Complete', lang)}"
        )
    if lang == "en":
        return (
            f"【Mock】Personal plan for {title} ({school}, {loc})\n\n"
            f"1. {t('mockStep1Docs', lang)}\n"
            f"2. {t('mockStep2Hours', lang, loc=loc)}\n"
            f"3. {t('mockStep3Orientation', lang)}\n"
            f"4. {t('mockStep4Complete', lang)}"
        )
    return (
        f"【Mock 模式】{t('mockPlanTitle', lang, title=title, school=school, loc=loc)}\n\n"
        f"1. {t('mockStep1Docs', lang)}\n"
        f"2. {t('mockStep2Hours', lang, loc=loc)}\n"
        f"3. {t('mockStep3Orientation', lang)}\n"
        f"4. {t('mockStep4Complete', lang)}"
    )
