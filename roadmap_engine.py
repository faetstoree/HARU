"""Roadmap engine: route resolution, task states, lock reasons, next tasks."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set

ROADMAP_PATH = os.path.join(os.path.dirname(__file__), "data", "roadmap.json")

from backend_i18n import t

SUPPORTED_LANGS = ("zh-TW", "en", "ja")
DEFAULT_LANG = "en"
BASELINE_START_PHASE = "phase_pre_arrival"

PRIORITY_ORDER = {"critical": 0, "high": 1, "normal": 2, "low": 3}


@lru_cache(maxsize=1)
def load_roadmap() -> Dict[str, Any]:
    with open(ROADMAP_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_lang(lang: Optional[str]) -> str:
    if not lang:
        return DEFAULT_LANG
    if lang in SUPPORTED_LANGS:
        return lang
    if lang.lower().startswith("zh"):
        return "zh-TW"
    if lang.lower().startswith("ja"):
        return "ja"
    return "en"


def pick_i18n(obj: Any, lang: str) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        lang = normalize_lang(lang)
        return obj.get(lang) or obj.get("en") or obj.get("zh-TW") or next(iter(obj.values()), "")
    return str(obj)


def is_actionable_task(task: Dict[str, Any]) -> bool:
    return task.get("kind", "action") not in ("awareness", "endpoint", "milestone")


def profile_from_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Build normalized profile from school_info / User fields."""
    housing = data.get("housing_type") or "dorm"
    if housing not in ("dorm", "rental", "housing_tbd"):
        housing = "dorm"
    part_time = data.get("part_time_plan") or "no"
    if part_time not in ("yes", "no", "later"):
        part_time = "no"
    school_type = data.get("school_type") or "language_school"
    if school_type not in ("language_school", "university", "vocational", "high_school"):
        school_type = "language_school"
    return {
        "housing_type": housing,
        "part_time_plan": part_time,
        "school_type": school_type,
        "sim_at_airport": bool(data.get("sim_at_airport", False)),
        "already_exchanged": bool(data.get("already_exchanged", False)),
        "has_residence_card": data.get("has_residence_card", True),
        "permit_obtained": bool(data.get("permit_obtained", False)),
    }


def _task_by_id(roadmap: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {t["id"]: t for t in roadmap["tasks"]}


def _route_config(roadmap: Dict[str, Any], housing_type: str) -> Dict[str, Any]:
    return roadmap["routes"].get(housing_type, roadmap["routes"]["dorm"])


def is_task_in_route(task: Dict[str, Any], profile: Dict[str, Any], roadmap: Dict[str, Any]) -> bool:
    housing = profile["housing_type"]
    route_cfg = _route_config(roadmap, housing)

    if task.get("part_time_only"):
        if profile["part_time_plan"] not in ("yes", "later"):
            return False

    excluded = set(route_cfg.get("exclude") or [])
    if task["id"] in excluded:
        return False

    task_routes = task.get("routes")
    if task_routes and housing not in task_routes:
        return False

    exclude_routes = task.get("exclude_routes") or []
    if housing in exclude_routes:
        return False

    skip_if = task.get("skip_if_profile") or {}
    for key, expected in skip_if.items():
        if profile.get(key) == expected:
            return False

    school_types = task.get("school_types")
    if school_types and profile.get("school_type", "language_school") not in school_types:
        return False

    return True


def resolve_effective_depends(task: Dict[str, Any], profile: Dict[str, Any]) -> List[str]:
    override = task.get("route_depends_override") or {}
    housing = profile["housing_type"]
    if housing in override:
        return list(override[housing])
    return list(task.get("depends_on") or [])


def resolve_active_task_ids(profile: Dict[str, Any], roadmap: Optional[Dict[str, Any]] = None) -> List[str]:
    roadmap = roadmap or load_roadmap()
    return [t["id"] for t in roadmap["tasks"] if is_task_in_route(t, profile, roadmap)]


def resolve_baseline_completed(
    profile: Dict[str, Any],
    roadmap: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Pre-arrival tasks assumed done when the student accesses Haru from Japan (e.g. airport)."""
    roadmap = roadmap or load_roadmap()
    profile = profile_from_dict(profile)
    baseline: List[str] = []
    for task in roadmap["tasks"]:
        if task.get("phase") != BASELINE_START_PHASE:
            continue
        if not is_task_in_route(task, profile, roadmap):
            continue
        if not is_actionable_task(task):
            continue
        baseline.append(task["id"])
    return baseline


def merge_effective_completed(
    profile: Dict[str, Any],
    completed: Optional[List[str]],
    roadmap: Optional[Dict[str, Any]] = None,
) -> List[str]:
    baseline = set(resolve_baseline_completed(profile, roadmap))
    user_done = set(completed or [])
    return sorted(baseline | user_done)


def get_task_state(
    task_id: str,
    profile: Dict[str, Any],
    completed: Set[str],
    roadmap: Optional[Dict[str, Any]] = None,
) -> str:
    """Returns: completed | available | locked | skipped"""
    roadmap = roadmap or load_roadmap()
    tasks = _task_by_id(roadmap)
    task = tasks.get(task_id)
    if not task:
        return "skipped"

    if not is_task_in_route(task, profile, roadmap):
        return "skipped"

    if task_id in completed:
        return "completed"

    deps = resolve_effective_depends(task, profile)
    for dep in deps:
        dep_task = tasks.get(dep)
        if not dep_task:
            continue
        if not is_task_in_route(dep_task, profile, roadmap):
            continue
        if dep not in completed:
            return "locked"

    return "available"


def get_lock_reason(
    task_id: str,
    profile: Dict[str, Any],
    completed: Set[str],
    lang: str,
    roadmap: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    roadmap = roadmap or load_roadmap()
    tasks = _task_by_id(roadmap)
    task = tasks.get(task_id)
    if not task:
        return None

    lang = normalize_lang(lang)
    deps = resolve_effective_depends(task, profile)
    missing = []
    for dep in deps:
        dep_task = tasks.get(dep)
        if not dep_task or not is_task_in_route(dep_task, profile, roadmap):
            continue
        if dep not in completed:
            missing.append(pick_i18n(dep_task["title"], lang))

    if not missing:
        return None
    prefix = t("lockReasonPrefix", lang)
    sep = t("lockReasonSep", lang)
    return prefix + sep.join(missing)


def get_next_tasks(
    profile: Dict[str, Any],
    completed: List[str],
    limit: int = 3,
    lang: str = DEFAULT_LANG,
    roadmap: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    roadmap = roadmap or load_roadmap()
    completed_set = set(completed)
    lang = normalize_lang(lang)
    phases = {p["id"]: p["order"] for p in roadmap["phases"]}
    available = []

    for task in roadmap["tasks"]:
        state = get_task_state(task["id"], profile, completed_set, roadmap)
        if state != "available":
            continue
        if not is_actionable_task(task):
            continue
        available.append({
            "id": task["id"],
            "title": pick_i18n(task["title"], lang),
            "summary": pick_i18n(task["summary"], lang),
            "phase": task["phase"],
            "priority": task.get("priority", "normal"),
            "phase_order": phases.get(task["phase"], 99),
        })

    available.sort(key=lambda x: (x["phase_order"], PRIORITY_ORDER.get(x["priority"], 9)))
    return available[:limit]


def _localize_task(task: Dict[str, Any], state: str, profile: Dict[str, Any], completed: Set[str], lang: str) -> Dict[str, Any]:
    lang = normalize_lang(lang)
    lock_reason = None
    if state == "locked":
        lock_reason = get_lock_reason(task["id"], profile, completed, lang)

    documents = []
    for d in task.get("documents") or []:
        documents.append({
            "id": d["id"],
            "label": pick_i18n(d.get("label"), lang),
            "required": d.get("required", True),
        })

    tips = [pick_i18n(tip, lang) for tip in (task.get("tips") or [])]

    return {
        "id": task["id"],
        "phase": task["phase"],
        "title": pick_i18n(task["title"], lang),
        "summary": pick_i18n(task["summary"], lang),
        "state": state,
        "lock_reason": lock_reason,
        "duration_min": task.get("duration_min"),
        "priority": task.get("priority", "normal"),
        "deadline_days_after_arrival": task.get("deadline_days_after_arrival"),
        "documents": documents,
        "tips": tips,
        "depends_on": resolve_effective_depends(task, profile),
        "kind": task.get("kind", "action"),
    }


def build_roadmap_response(
    profile: Dict[str, Any],
    completed: List[str],
    lang: str = DEFAULT_LANG,
    roadmap: Optional[Dict[str, Any]] = None,
    branch_choices: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    from roadmap_branch_engine import (
        build_branch_choices_summary,
        get_branch_point_for_task,
        get_task_state_with_branches,
        localize_supplemental_task,
        merge_supplemental_tasks,
    )

    roadmap = roadmap or load_roadmap()
    profile = profile_from_dict(profile) if "housing_type" not in profile else profile
    branch_choices = branch_choices or {}
    user_completed = list(completed or [])
    effective_completed = merge_effective_completed(profile, user_completed, roadmap)
    completed_set = set(effective_completed)
    lang = normalize_lang(lang)

    supplemental = merge_supplemental_tasks(roadmap, profile, branch_choices)
    supp_by_parent: Dict[str, List[Dict[str, Any]]] = {}
    for st in supplemental:
        parent = st.get("branch_parent")
        if parent:
            supp_by_parent.setdefault(parent, []).append(st)

    active_base = set(resolve_active_task_ids(profile, roadmap))
    active_supp = {t["id"] for t in supplemental}
    active_ids = active_base | active_supp
    done_count = len([
        t for t in active_ids
        if is_actionable_task(_task_by_id(roadmap).get(t, {}))
        and get_task_state_with_branches(t, profile, completed_set, branch_choices, roadmap) == "completed"
    ])
    total_active = len([
        t for t in active_ids
        if is_actionable_task(_task_by_id(roadmap).get(t, {}))
        and get_task_state_with_branches(t, profile, completed_set, branch_choices, roadmap) != "skipped"
    ])

    phases_out = []
    for phase in sorted(roadmap["phases"], key=lambda p: p["order"]):
        phase_tasks = []
        for task in roadmap["tasks"]:
            if task["phase"] != phase["id"]:
                continue
            state = get_task_state_with_branches(task["id"], profile, completed_set, branch_choices, roadmap)
            if state == "skipped":
                continue
            loc = _localize_task(task, state, profile, completed_set, lang)
            bp = get_branch_point_for_task(task["id"], profile, branch_choices, lang, roadmap)
            if bp:
                loc["branch_point"] = bp
            loc["has_branch_children"] = bool(supp_by_parent.get(task["id"]))
            phase_tasks.append(loc)

            for stask in supp_by_parent.get(task["id"], []):
                if stask["phase"] != phase["id"]:
                    continue
                sstate = get_task_state_with_branches(stask["id"], profile, completed_set, branch_choices, roadmap)
                if sstate == "skipped":
                    continue
                phase_tasks.append(
                    localize_supplemental_task(stask, sstate, profile, completed_set, lang, branch_choices, roadmap)
                )

        phases_out.append({
            "id": phase["id"],
            "order": phase["order"],
            "title": pick_i18n(phase["title"], lang),
            "tasks": phase_tasks,
        })

    next_tasks = _get_next_tasks_with_branches(
        profile, effective_completed, branch_choices, limit=3, lang=lang, roadmap=roadmap
    )
    route_cfg = _route_config(roadmap, profile["housing_type"])

    from roadmap_graph_engine import build_roadmap_graph

    return {
        "route": {
            "id": profile["housing_type"],
            "label": pick_i18n(route_cfg["label"], lang),
        },
        "progress": {
            "completed": done_count,
            "total": total_active,
            "percent": round(100 * done_count / total_active) if total_active else 0,
        },
        "phases": phases_out,
        "next_tasks": next_tasks,
        "completed_tasks": user_completed,
        "baseline_completed": resolve_baseline_completed(profile, roadmap),
        "effective_completed": effective_completed,
        "branch_choices": branch_choices,
        "branch_summary": build_branch_choices_summary(branch_choices, lang),
        "graph": build_roadmap_graph(profile, effective_completed, lang, branch_choices, roadmap),
    }


def _get_next_tasks_with_branches(
    profile: Dict[str, Any],
    completed: List[str],
    branch_choices: Dict[str, str],
    limit: int = 3,
    lang: str = DEFAULT_LANG,
    roadmap: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    from roadmap_branch_engine import get_task_state_with_branches, merge_supplemental_tasks

    roadmap = roadmap or load_roadmap()
    completed_set = set(completed)
    lang = normalize_lang(lang)
    phases = {p["id"]: p["order"] for p in roadmap["phases"]}
    available = []

    all_task_defs = list(roadmap["tasks"]) + merge_supplemental_tasks(roadmap, profile, branch_choices)
    for task in all_task_defs:
        if not is_actionable_task(task):
            continue
        state = get_task_state_with_branches(task["id"], profile, completed_set, branch_choices, roadmap)
        if state != "available":
            continue
        available.append({
            "id": task["id"],
            "title": pick_i18n(task["title"], lang),
            "summary": pick_i18n(task["summary"], lang),
            "phase": task["phase"],
            "priority": task.get("priority", "normal"),
            "phase_order": phases.get(task["phase"], 99),
            "is_branch_child": bool(task.get("branch_parent")),
        })

    available.sort(key=lambda x: (x["phase_order"], PRIORITY_ORDER.get(x["priority"], 9)))
    return available[:limit]


def get_all_task_ids_for_onboarding(profile: Dict[str, Any], lang: str = DEFAULT_LANG, roadmap: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    """Task list for onboarding checkboxes (excludes pre-arrival baseline tasks)."""
    roadmap = roadmap or load_roadmap()
    profile = profile_from_dict(profile)
    lang = normalize_lang(lang)
    result = []
    for task in roadmap["tasks"]:
        if task.get("phase") == BASELINE_START_PHASE:
            continue
        if not is_task_in_route(task, profile, roadmap):
            continue
        if not is_actionable_task(task):
            continue
        result.append({
                "id": task["id"],
                "title": pick_i18n(task["title"], lang),
                "phase": task["phase"],
            })
    return result
