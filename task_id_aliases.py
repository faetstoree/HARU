"""Legacy roadmap task ID to v3 canonical IDs (roadmap v3.0)."""
from __future__ import annotations

from typing import Dict, List, Set, Union

# Old task_id -> new id or list of ids (for resources spanning multiple routes)
TASK_ID_ALIASES: Dict[str, Union[str, List[str]]] = {
    "task_arrival": "task_immigration",
    "task_residence_card": "task_immigration",
    "task_residence_expiry": "task_id_documents",
    "task_address": "task_ward_office",
    "task_housing_confirm": "task_move_in",
    "task_insurance": "task_ward_office",
    "task_pension": "task_pension_student",
    "task_mynumber": "task_mynumber_notice",
    "task_exchange": "task_immigration",
    "task_transport_card": "task_transport",
    "task_contact_school": "task_school_enroll",
    "task_orientation": "task_school_enroll",
    "task_emergency_guide": "task_basics_complete",
    "task_disaster_prep": "task_basics_complete",
    "task_scam_awareness": "task_basics_complete",
    "task_healthcare_guide": "task_ward_office",
    "task_essentials": "task_move_in",
    "task_temp_stay": "task_move_in",
    "task_find_housing": [
        "task_housing_dorm",
        "task_housing_rental_managed",
        "task_housing_rental_self",
    ],
    "task_lease": "task_housing_rental_managed",
}


def canonical_task_ids(task_id: str) -> List[str]:
    """Resolve a task id to one or more canonical v3 ids."""
    if not task_id:
        return []
    mapped = TASK_ID_ALIASES.get(task_id)
    if mapped is None:
        return [task_id]
    if isinstance(mapped, list):
        return list(mapped)
    return [mapped]


def expand_task_id_set(task_id: str) -> Set[str]:
    """IDs that should match when looking up content for a task (includes legacy aliases)."""
    out: Set[str] = {task_id}
    out.update(canonical_task_ids(task_id))
    for old, new in TASK_ID_ALIASES.items():
        targets = new if isinstance(new, list) else [new]
        if task_id in targets or task_id == old:
            out.add(old)
            out.update(targets)
    return out


def migrate_task_id_list(task_ids: List[str]) -> List[str]:
    """Replace legacy ids in a list; dedupe preserving order."""
    out: List[str] = []
    seen: Set[str] = set()
    for tid in task_ids or []:
        for cid in canonical_task_ids(tid):
            if cid not in seen:
                seen.add(cid)
                out.append(cid)
    return out


def task_ids_overlap(query_task_id: str, stored_task_ids: List[str]) -> bool:
    """True if query task (or its aliases) overlaps stored task_ids."""
    if not query_task_id or not stored_task_ids:
        return False
    query_set = expand_task_id_set(query_task_id)
    stored_set: Set[str] = set()
    for tid in stored_task_ids:
        stored_set.update(expand_task_id_set(tid))
    return bool(query_set & stored_set)
