"""Build personalized action-plan content (agent-driven, not a full data dump)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from agent_engine import build_rule_based_decision
from roadmap_engine import normalize_lang
from backend_i18n import t

# Task-specific actionable steps (2nd person, ordered)
TASK_STEPS: Dict[str, Dict[str, List[str]]] = {
    "task_ward_office": {
        "zh-TW": [
            "確認今天是否為平日（區役所通常週末休息）",
            "準備護照、在留卡、租房合約或宿舍證明",
            "前往居住地所屬區役所，辦理住民登錄、國民健康保險（20歲以上另辦國民年金）",
            "同時申請保險料減免，並請求記載マイナンバーの住民票副本",
        ],
        "en": [
            "Check if today is a weekday (ward offices are usually closed on weekends)",
            "Prepare passport, residence card, and lease or dorm proof",
            "Visit your ward office for resident registration, national health insurance (and pension if 20+)",
            "Apply for premium reduction and request a resident record copy with My Number",
        ],
        "ja": [
            "平日かどうか確認する（区役所は土日休みが多い）",
            "パスポート・在留カード・賃貸契約または寮の証明を準備",
            "区役所で住民登録・国保加入（20歳以上は国年も）",
            "保険料減免申請とマイナンバー記載の住民票の写しを同時に取得",
        ],
    },
    "task_bank": {
        "zh-TW": [
            "確認已拿到住民票與日本手機號碼",
            "攜帶護照、在留卡、住民票、印章（如有）",
            "前往附近的ゆうちょ銀行或郵局窗口辦理開戶",
            "開戶後記下帳號，學費與房租轉帳會用到",
        ],
        "en": [
            "Make sure you have your resident certificate and Japanese phone number",
            "Bring passport, residence card, resident certificate, and hanko if you have one",
            "Visit a nearby Japan Post Bank branch to open an account",
            "Save your account number for tuition and rent transfers",
        ],
        "ja": [
            "住民票と日本の携帯番号を取得済みか確認",
            "パスポート・在留カード・住民票・印鑑（あれば）を持参",
            "近くのゆうちょ銀行で口座開設",
            "学費・家賃の振込用に口座番号を控える",
        ],
    },
    "task_phone": {
        "zh-TW": [
            "確認已完成住民登錄（多數電信方案需要）",
            "比較 SIM 卡與月租方案（學生向短期方案可考慮）",
            "攜帶護照、在留卡、住民票前往門市或辦理線上申請",
            "開通後測試通話與網路，並保留契約文件",
        ],
        "en": [
            "Confirm resident registration is done (required by most carriers)",
            "Compare SIM and monthly plans (short-term student plans are available)",
            "Bring passport, residence card, and resident certificate to a store",
            "Test calls and data after activation; keep your contract",
        ],
        "ja": [
            "住民登録が完了しているか確認（多くの契約で必要）",
            "SIMと月額プランを比較（留学生向け短期プランもあり）",
            "パスポート・在留カード・住民票を持って店舗へ",
            "開通後に通話とデータを確認し、契約書を保管",
        ],
    },
}


def _find_task_detail(roadmap_data: Dict[str, Any], task_id: str) -> Optional[Dict[str, Any]]:
    for phase in roadmap_data.get("phases", []):
        for task in phase.get("tasks", []):
            if task.get("id") == task_id:
                return {**task, "phase_title": phase.get("title", "")}
    return None


def _default_steps(task: Dict[str, Any], lang: str) -> List[str]:
    lang = normalize_lang(lang)
    tid = task.get("id", "")
    if tid in TASK_STEPS:
        return TASK_STEPS[tid].get(lang, TASK_STEPS[tid]["zh-TW"])
    summary = task.get("summary") or ""
    return [
        t("stepReadSummary", lang, summary=summary),
        t("stepPrepDocs", lang),
        t("stepMarkComplete", lang),
    ]


def build_action_plan_content(
    roadmap_data: Dict[str, Any],
    school_info: Dict[str, Any],
    lang: str = "zh-TW",
    current_address: str = "",
) -> Dict[str, Any]:
    """Compose a single-student action plan from roadmap + agent engine."""
    lang = normalize_lang(lang)
    decision = build_rule_based_decision(
        roadmap_data, school_info, lang, current_address or school_info.get("location", "")
    )
    next_tasks: List[Dict[str, Any]] = roadmap_data.get("next_tasks") or []
    focus_brief = next_tasks[0] if next_tasks else None
    focus = _find_task_detail(roadmap_data, focus_brief["id"]) if focus_brief else None

    completed_milestones: List[str] = []
    for phase in roadmap_data.get("phases", []):
        for task in phase.get("tasks", []):
            if task.get("state") == "completed":
                completed_milestones.append(task.get("title", ""))

    upcoming: List[Dict[str, str]] = []
    for task in next_tasks[1:4]:
        upcoming.append({
            "title": task.get("title", ""),
            "summary": (task.get("summary") or "")[:120],
        })

    path_ahead: List[Dict[str, Any]] = []
    for phase in roadmap_data.get("phases", []):
        remaining = [
            {
                "title": task.get("title", ""),
                "state": task.get("state", ""),
                "lock_reason": task.get("lock_reason") or "",
            }
            for task in phase.get("tasks", [])
            if task.get("state") != "completed"
        ]
        if remaining:
            path_ahead.append({"phase": phase.get("title", ""), "tasks": remaining})

    now = datetime.now(ZoneInfo("Asia/Tokyo"))
    greeting = t(
        "greetingBody", lang,
        location=school_info.get("location", "日本" if lang == "zh-TW" else ("Japan" if lang == "en" else "日本")),
        school_name=school_info.get("school_name", "語言學校" if lang == "zh-TW" else ("your school" if lang == "en" else "学校")),
        completed=roadmap_data["progress"]["completed"],
        total=roadmap_data["progress"]["total"],
    )

    if not focus:
        return {
            "lang": lang,
            "generated_at": now.strftime("%Y-%m-%d %H:%M JST"),
            "school_info": school_info,
            "progress": roadmap_data["progress"],
            "route_label": roadmap_data.get("route", {}).get("label", ""),
            "greeting": greeting,
            "agent_message": decision.get("narrative", ""),
            "all_done": True,
            "focus": None,
            "steps": [],
            "upcoming": [],
            "path_ahead": [],
            "completed_milestones": completed_milestones,
        }

    steps = _default_steps(focus, lang)
    if focus.get("lock_reason"):
        steps.insert(0, t("stepPrerequisite", lang, reason=focus["lock_reason"]))

    return {
        "lang": lang,
        "generated_at": now.strftime("%Y-%m-%d %H:%M JST"),
        "school_info": school_info,
        "progress": roadmap_data["progress"],
        "route_label": roadmap_data.get("route", {}).get("label", ""),
        "greeting": greeting,
        "agent_message": decision.get("narrative", ""),
        "agent_where": decision.get("action_data", ""),
        "upcoming_hint": decision.get("upcoming_hint", ""),
        "all_done": False,
        "focus": {
            "title": focus.get("title", ""),
            "phase": focus.get("phase_title", ""),
            "summary": focus.get("summary", ""),
            "duration_min": focus.get("duration_min"),
            "deadline_days": focus.get("deadline_days_after_arrival"),
            "documents": [d.get("label", "") for d in (focus.get("documents") or [])],
            "tips": focus.get("tips") or [],
            "official_links": focus.get("official_links") or [],
        },
        "steps": steps,
        "upcoming": upcoming,
        "path_ahead": path_ahead,
        "completed_milestones": completed_milestones[-6:],
    }
