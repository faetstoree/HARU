"""Roadmap -> Mermaid flowcharts for in-chat diagrams."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from roadmap_engine import build_roadmap_response, normalize_lang, pick_i18n, profile_from_dict
from backend_i18n import t


def _lang_key(lang: str) -> str:
    return lang if lang in ("zh-TW", "en", "ja") else "en"


def _mermaid_id(raw: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", raw or "node")
    if not safe:
        safe = "node"
    if safe[0].isdigit():
        safe = f"n_{safe}"
    return safe


def _escape_label(label: str) -> str:
    text = (label or "").replace('"', "'").replace("\n", " ").strip()
    return text[:56] if text else "\u2026"


def _state_class(state: str) -> str:
    return {
        "completed": "haruDone",
        "available": "haruActive",
        "locked": "haruLocked",
        "alternative": "haruAlt",
        "selected_path": "haruActive",
        "skipped": "haruLocked",
    }.get(state or "", "haruNeutral")


def _collect_tasks(roadmap_resp: Dict[str, Any]) -> List[Dict[str, Any]]:
    tasks: List[Dict[str, Any]] = []
    for phase in roadmap_resp.get("phases") or []:
        phase_title = phase.get("title") or phase.get("id") or ""
        for task in phase.get("tasks") or []:
            if task.get("state") == "skipped":
                continue
            tasks.append({**task, "phase_id": phase.get("id"), "phase_title": phase_title})
    return tasks


def _select_tasks(
    roadmap_resp: Dict[str, Any],
    scope: str,
    highlight_task_id: Optional[str],
    max_tasks: int,
) -> List[Dict[str, Any]]:
    all_tasks = _collect_tasks(roadmap_resp)
    if not all_tasks:
        return []

    scope = (scope or "next_steps").lower()
    if scope == "full":
        return all_tasks[:max_tasks]

    if scope == "current_phase":
        focus = highlight_task_id
        if not focus:
            nxt = roadmap_resp.get("next_tasks") or []
            focus = nxt[0]["id"] if nxt else all_tasks[0]["id"]
        phase_id = None
        for task in all_tasks:
            if task["id"] == focus:
                phase_id = task.get("phase_id") or task.get("phase")
                break
        if phase_id:
            phase_tasks = [t for t in all_tasks if (t.get("phase_id") or t.get("phase")) == phase_id]
            return phase_tasks[:max_tasks]
        return all_tasks[:max_tasks]

    # next_steps (default)
    selected: Set[str] = set()
    for task in (roadmap_resp.get("next_tasks") or [])[:5]:
        selected.add(task["id"])
    id_map = {t["id"]: t for t in all_tasks}
    expanded = set(selected)
    for tid in list(selected):
        task = id_map.get(tid)
        if not task:
            continue
        for dep in task.get("depends_on") or []:
            if dep in id_map:
                expanded.add(dep)
    ordered = [t for t in all_tasks if t["id"] in expanded]
    if len(ordered) < 2:
        ordered = all_tasks[: min(max_tasks, 8)]
    return ordered[:max_tasks]


def roadmap_to_mermaid_source(
    profile: Dict[str, Any],
    completed: List[str],
    lang: str = "ja",
    *,
    scope: str = "next_steps",
    highlight_task_id: Optional[str] = None,
    branch_choices: Optional[Dict[str, str]] = None,
    max_tasks: int = 15,
) -> str:
    lang = normalize_lang(lang)
    profile = profile_from_dict(profile)
    roadmap_resp = build_roadmap_response(
        profile,
        completed,
        lang,
        branch_choices=branch_choices or {},
    )
    tasks = _select_tasks(roadmap_resp, scope, highlight_task_id, max_tasks)
    if not tasks:
        return "flowchart TD\n  empty[\"No tasks to show\"]"

    allowed_ids = {t["id"] for t in tasks}
    lines: List[str] = ["flowchart TD"]
    phase_ids: Dict[str, str] = {}

    current_phase = None
    for task in tasks:
        phase_title = task.get("phase_title") or task.get("phase_id") or ""
        phase_key = task.get("phase_id") or task.get("phase") or "phase"
        if phase_key != current_phase:
            if current_phase is not None:
                lines.append("  end")
            subgraph_id = _mermaid_id(f"sub_{phase_key}")
            phase_ids[phase_key] = subgraph_id
            lines.append(f'  subgraph {subgraph_id} ["{_escape_label(phase_title)}"]')
            current_phase = phase_key

        node_id = _mermaid_id(task["id"])
        label = _escape_label(task.get("title") or task["id"])
        lines.append(f'    {node_id}["{label}"]')

    if current_phase is not None:
        lines.append("  end")

    for task in tasks:
        node_id = _mermaid_id(task["id"])
        deps = [d for d in (task.get("depends_on") or []) if d in allowed_ids]
        if not deps and tasks[0]["id"] != task["id"]:
            prev_idx = tasks.index(task) - 1
            if prev_idx >= 0:
                deps = [tasks[prev_idx]["id"]]
        for dep in deps:
            lines.append(f"  {_mermaid_id(dep)} --> {node_id}")

    lines.extend([
        "  classDef haruDone fill:#c8f250,stroke:#4f6600,color:#191c20",
        "  classDef haruActive fill:#7764ce,stroke:#5e4bb3,color:#ffffff",
        "  classDef haruLocked fill:#e7e8ee,stroke:#797583,color:#484552",
        "  classDef haruAlt fill:#ededf3,stroke:#c9c4d4,color:#484552",
        "  classDef haruNeutral fill:#f3f3f9,stroke:#c9c4d4,color:#191c20",
        "  classDef haruFocus fill:#f3b5d3,stroke:#5e4bb3,color:#340d24,stroke-width:2px",
    ])

    for task in tasks:
        cls = _state_class(task.get("state") or "")
        lines.append(f"  class {_mermaid_id(task['id'])} {cls}")

    focus = highlight_task_id or ((roadmap_resp.get("next_tasks") or [{}])[0].get("id"))
    if focus and focus in allowed_ids:
        lines.append(f"  class {_mermaid_id(focus)} haruFocus")

    return "\n".join(lines)


def build_mermaid_block(
    source: str,
    lang: str = "ja",
    *,
    title: Optional[str] = None,
    diagram_kind: str = "custom",
) -> Dict[str, Any]:
    src = (source or "").strip()
    if not src:
        src = "flowchart TD\n  empty[\"Empty diagram\"]"
    elif not re.match(r"^(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram|erDiagram|gantt|pie|gitGraph)\b", src):
        src = f"flowchart TD\n{src}"
    return {
        "type": "mermaid",
        "title": title or "",
        "source": src,
        "diagram_kind": diagram_kind,
    }


def build_roadmap_mermaid_block(
    profile: Dict[str, Any],
    completed: List[str],
    lang: str = "ja",
    *,
    scope: str = "next_steps",
    highlight_task_id: Optional[str] = None,
    branch_choices: Optional[Dict[str, str]] = None,
    title: Optional[str] = None,
) -> Dict[str, Any]:
    lang_key = _lang_key(lang)
    scope_key = scope if scope in ("next_steps", "current_phase", "full") else "next_steps"
    title_key = {"next_steps": "mermaidNextSteps", "current_phase": "mermaidCurrentPhase", "full": "mermaidFull"}[scope_key]
    default_title = t(title_key, lang_key)
    source = roadmap_to_mermaid_source(
        profile,
        completed,
        lang,
        scope=scope_key,
        highlight_task_id=highlight_task_id,
        branch_choices=branch_choices,
    )
    return build_mermaid_block(
        source,
        lang,
        title=title or default_title,
        diagram_kind="roadmap",
    )


def looks_like_roadmap_query(message: str) -> bool:
    lower = (message or "").lower()
    keywords = (
        "roadmap", "flowchart", "mermaid", "diagram", "flow chart",
        "\u624b\u7d9a\u304d", "\u6d41\u308c", "\u30ed\u30fc\u30c9\u30de\u30c3\u30d7", "\u843d\u5730", "\u30d5\u30ed\u30fc",
        "\u5168\u4f53\u50cf", "\u5de5\u7a0b", "\u6d41\u7a0b", "\u8def\u7dda\u56f3", "\u6b21\u306b", "\u624b\u9806", "\u56f3\u3067",
        "\u6d41\u7a0b", "\u8def\u7dda\u5716", "\u63a5\u4e0b\u6765", "\u4e0b\u4e00\u6b65",
    )
    return any(k in lower for k in keywords)
