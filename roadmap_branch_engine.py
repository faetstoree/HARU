"""User-selectable roadmap branches and supplemental sub-tasks."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set

from roadmap_engine import (
    get_lock_reason,
    get_task_state,
    is_task_in_route,
    load_roadmap,
    normalize_lang,
    pick_i18n,
    profile_from_dict,
    resolve_effective_depends,
)

BRANCHES_PATH = os.path.join(os.path.dirname(__file__), "data", "roadmap_branches.json")


@lru_cache(maxsize=1)
def load_branches() -> Dict[str, Any]:
    if not os.path.exists(BRANCHES_PATH):
        return {"branch_points": [], "supplemental_tasks": [], "completion_aliases": {}}
    with open(BRANCHES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def expand_completed_set(completed: Set[str]) -> Set[str]:
    """Treat branch-child completion as parent completion for dependencies."""
    aliases = load_branches().get("completion_aliases") or {}
    expanded = set(completed)
    for parent, children in aliases.items():
        if parent in expanded:
            continue
        if any(c in expanded for c in children):
            expanded.add(parent)
    return expanded


def _branch_point_applies(bp: Dict[str, Any], profile: Dict[str, Any], roadmap: Dict[str, Any]) -> bool:
    task_id = bp.get("task_id")
    if not task_id:
        return False
    tasks = {t["id"]: t for t in roadmap["tasks"]}
    task = tasks.get(task_id)
    if not task or not is_task_in_route(task, profile, roadmap):
        return False
    if bp.get("part_time_only") and profile.get("part_time_plan") not in ("yes", "later"):
        return False
    only_if = bp.get("only_if_profile") or {}
    for key, expected in only_if.items():
        if profile.get(key) != expected:
            return False
    return True


def localize_branch_point(bp: Dict[str, Any], lang: str, selected: Optional[str] = None) -> Dict[str, Any]:
    lang = normalize_lang(lang)
    choices = []
    for c in bp.get("choices") or []:
        choices.append({
            "id": c["id"],
            "label": pick_i18n(c.get("label"), lang),
            "description": pick_i18n(c.get("description"), lang),
            "unlock_tasks": c.get("unlock_tasks") or [],
        })
    return {
        "id": bp["id"],
        "task_id": bp["task_id"],
        "prompt": pick_i18n(bp.get("prompt"), lang),
        "choices": choices,
        "selected": selected,
    }


def get_branch_point_for_task(
    task_id: str,
    profile: Dict[str, Any],
    branch_choices: Dict[str, str],
    lang: str,
    roadmap: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    roadmap = roadmap or load_roadmap()
    profile = profile_from_dict(profile) if "housing_type" not in profile else profile
    for bp in load_branches().get("branch_points") or []:
        if bp.get("task_id") != task_id:
            continue
        if not _branch_point_applies(bp, profile, roadmap):
            continue
        return localize_branch_point(bp, lang, branch_choices.get(bp["id"]))
    return None


def is_supplemental_task_visible(
    stask: Dict[str, Any],
    profile: Dict[str, Any],
    branch_choices: Dict[str, str],
    roadmap: Dict[str, Any],
) -> bool:
    required = stask.get("branch_required") or {}
    for bp_id, choice_id in required.items():
        if branch_choices.get(bp_id) != choice_id:
            return False
    parent_id = stask.get("branch_parent")
    if parent_id:
        tasks = {t["id"]: t for t in roadmap["tasks"]}
        parent = tasks.get(parent_id)
        if parent and not is_task_in_route(parent, profile, roadmap):
            return False
    return True


def get_hidden_task_ids(branch_choices: Dict[str, str]) -> Set[str]:
    hidden: Set[str] = set()
    for bp in load_branches().get("branch_points") or []:
        selected = branch_choices.get(bp["id"])
        if not selected:
            continue
        for c in bp.get("choices") or []:
            if c["id"] == selected:
                hidden.update(c.get("hide_tasks") or [])
    return hidden


def merge_supplemental_tasks(
    roadmap: Dict[str, Any],
    profile: Dict[str, Any],
    branch_choices: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Return supplemental task defs visible for current branch choices."""
    hidden = get_hidden_task_ids(branch_choices)
    out = []
    for stask in load_branches().get("supplemental_tasks") or []:
        if stask["id"] in hidden:
            continue
        if not is_supplemental_task_visible(stask, profile, branch_choices, roadmap):
            continue
        out.append(stask)
    return out


def get_all_tasks_for_engine(
    roadmap: Optional[Dict[str, Any]] = None,
    profile: Optional[Dict[str, Any]] = None,
    branch_choices: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    roadmap = roadmap or load_roadmap()
    profile = profile or profile_from_dict({})
    branch_choices = branch_choices or {}
    base = list(roadmap["tasks"])
    supplemental = merge_supplemental_tasks(roadmap, profile, branch_choices)
    return base + supplemental


def get_task_state_with_branches(
    task_id: str,
    profile: Dict[str, Any],
    completed: Set[str],
    branch_choices: Dict[str, str],
    roadmap: Optional[Dict[str, Any]] = None,
) -> str:
    roadmap = roadmap or load_roadmap()
    all_tasks = {t["id"]: t for t in get_all_tasks_for_engine(roadmap, profile, branch_choices)}
    task = all_tasks.get(task_id)
    if not task:
        return "skipped"

    if task_id in (load_branches().get("completion_aliases") or {}):
        children = (load_branches().get("completion_aliases") or {}).get(task_id, [])
        if any(c in completed for c in children):
            return "completed" if task_id in completed else "available"

    if not task.get("branch_parent"):
        if not is_task_in_route(task, profile, roadmap):
            return "skipped"
    else:
        if not is_supplemental_task_visible(task, profile, branch_choices, roadmap):
            return "skipped"

    expanded = expand_completed_set(completed)
    if task_id in expanded:
        return "completed"

    deps = list(task.get("depends_on") or [])
    if task.get("branch_parent") and not deps:
        deps = [task["branch_parent"]]

    for dep in deps:
        dep_task = all_tasks.get(dep)
        if not dep_task:
            continue
        if dep_task.get("branch_parent"):
            if not is_supplemental_task_visible(dep_task, profile, branch_choices, roadmap):
                continue
        elif not is_task_in_route(dep_task, profile, roadmap):
            continue
        dep_expanded = expand_completed_set(completed)
        if dep not in dep_expanded:
            return "locked"

    return "available"


def localize_supplemental_task(
    task: Dict[str, Any],
    state: str,
    profile: Dict[str, Any],
    completed: Set[str],
    lang: str,
    branch_choices: Dict[str, str],
    roadmap: Dict[str, Any],
) -> Dict[str, Any]:
    lang = normalize_lang(lang)
    lock_reason = None
    if state == "locked":
        lock_reason = get_lock_reason(task["id"], profile, completed, lang, roadmap)

    documents = []
    for d in task.get("documents") or []:
        documents.append({
            "id": d.get("id", d.get("label", "doc")),
            "label": pick_i18n(d.get("label"), lang) if isinstance(d.get("label"), dict) else str(d.get("label", "")),
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
        "depends_on": list(task.get("depends_on") or []),
        "is_branch_child": True,
        "branch_parent": task.get("branch_parent"),
    }


def build_branch_choices_summary(branch_choices: Dict[str, str], lang: str) -> List[Dict[str, str]]:
    lang = normalize_lang(lang)
    summary = []
    for bp in load_branches().get("branch_points") or []:
        cid = branch_choices.get(bp["id"])
        if not cid:
            continue
        choice = next((c for c in bp.get("choices") or [] if c["id"] == cid), None)
        if choice:
            summary.append({
                "branch_id": bp["id"],
                "choice_id": cid,
                "label": pick_i18n(choice.get("label"), lang),
            })
    return summary
