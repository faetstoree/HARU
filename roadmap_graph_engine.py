"""Layer-based roadmap graph — topological layout with branch forks and route integration."""
from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional, Set, Tuple

from roadmap_branch_engine import (
    get_branch_point_for_task,
    get_task_state_with_branches,
    load_branches,
    localize_supplemental_task,
)
from roadmap_engine import (
    _localize_task,
    is_task_in_route,
    load_roadmap,
    normalize_lang,
    pick_i18n,
    profile_from_dict,
    resolve_effective_depends,
)
from backend_i18n import t

LAYER_W = 224
LANE_H = 88
PAD_X = 44
PAD_Y = 56
HEADER_H = 36
NODE_H = 64
NODE_W = 196
FORK_SIZE = 34


def _supplemental_by_id() -> Dict[str, Dict[str, Any]]:
    return {t["id"]: t for t in load_branches().get("supplemental_tasks") or []}


def _topo_sort_tasks(tasks: List[Dict[str, Any]], profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    task_map = {t["id"]: t for t in tasks}
    indeg: Dict[str, int] = {t["id"]: 0 for t in tasks}
    adj: Dict[str, List[str]] = {t["id"]: [] for t in tasks}
    for t in tasks:
        for dep in resolve_effective_depends(t, profile):
            if dep in task_map:
                adj[dep].append(t["id"])
                indeg[t["id"]] += 1
    q = deque([tid for tid, d in indeg.items() if d == 0])
    order: List[str] = []
    while q:
        tid = q.popleft()
        order.append(tid)
        for nxt in adj[tid]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                q.append(nxt)
    if len(order) != len(tasks):
        order = [t["id"] for t in tasks]
    return [task_map[tid] for tid in order]


def _route_exclusive_tasks(roadmap: Dict[str, Any], housing: str) -> Dict[str, List[Dict[str, Any]]]:
    """Key tasks exclusive to each housing route."""
    by_route: Dict[str, List[Dict[str, Any]]] = {r: [] for r in roadmap["routes"]}
    for task in roadmap["tasks"]:
        routes = task.get("routes")
        if not routes:
            continue
        for r in routes:
            if r in by_route:
                by_route[r].append(task)
    return by_route


def build_roadmap_graph(
    profile: Dict[str, Any],
    completed: List[str],
    lang: str = "zh-TW",
    branch_choices: Optional[Dict[str, str]] = None,
    roadmap: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    roadmap = roadmap or load_roadmap()
    profile = profile_from_dict(profile) if "housing_type" not in profile else profile
    branch_choices = branch_choices or {}
    completed_set = set(completed)
    lang = normalize_lang(lang)
    supp_map = _supplemental_by_id()
    housing = profile["housing_type"]

    phases = sorted(roadmap["phases"], key=lambda p: p["order"])
    phase_order = {p["id"]: p["order"] for p in phases}
    phase_title = {p["id"]: pick_i18n(p["title"], lang) for p in phases}

    active_tasks = [
        t for t in roadmap["tasks"]
        if is_task_in_route(t, profile, roadmap)
        and get_task_state_with_branches(t["id"], profile, completed_set, branch_choices, roadmap) != "skipped"
    ]
    sorted_tasks = _topo_sort_tasks(active_tasks, profile)

    graph_nodes: List[Dict[str, Any]] = []
    graph_edges: List[Dict[str, Any]] = []
    node_ids: Set[str] = set()
    layer_slots: Dict[int, List[int]] = {}

    def reserve_lane(layer: int, preferred: int = 0) -> int:
        used = set(layer_slots.setdefault(layer, []))
        lane = preferred
        while lane in used:
            lane += 1
        layer_slots[layer].append(lane)
        return lane

    def add_node(node: Dict[str, Any]) -> str:
        if node["id"] in node_ids:
            return node["id"]
        node_ids.add(node["id"])
        graph_nodes.append(node)
        return node["id"]

    def add_edge(fr: str, to: str, edge_type: str = "flow", active: bool = True) -> None:
        if fr == to:
            return
        graph_edges.append({"from": fr, "to": to, "type": edge_type, "active": active})

    def place(node_id: str, layer: int, lane: int, **extra) -> None:
        for n in graph_nodes:
            if n["id"] == node_id:
                n["layer"] = layer
                n["lane"] = lane
                n.update(extra)
                return

    housing_fork_done = False
    layer = 0
    prev_exit: Optional[Tuple[str, int]] = None  # (node_id, lane)

    def connect_prev(target_id: str, target_lane: int) -> None:
        nonlocal prev_exit
        if not prev_exit:
            return
        fr, fl = prev_exit
        add_edge(fr, target_id, "flow", True)
        if fl != target_lane:
            add_edge(fr, target_id, "merge", True)

    for task in sorted_tasks:
        # Housing route fork (once, at first housing-phase task)
        if not housing_fork_done and task.get("routes") and task["phase"] == "phase_pre_arrival":
            housing_fork_done = True
            fork_id = "fork_housing_route"
            route_labels = {
                r: pick_i18n(roadmap["routes"][r]["label"], lang)
                for r in roadmap["routes"]
            }
            flane = reserve_lane(layer, 0)
            add_node({
                "id": fork_id,
                "node_type": "fork",
                "task_id": None,
                "label": t("graphHousingForkLabel", lang),
                "state": "completed",
                "phase_id": "phase_pre_arrival",
                "branch_id": "housing_route",
                "meta": {"prompt": t("graphHousingForkPrompt", lang), "selected": housing},
            })
            place(fork_id, layer, flane)
            connect_prev(fork_id, flane)
            layer += 1

            exclusive = _route_exclusive_tasks(roadmap, housing)
            choice_lanes: List[Tuple[str, int, str]] = []
            for ri, route_id in enumerate(["dorm", "rental", "housing_tbd"]):
                selected = route_id == housing
                preview_id = f"route_path_{route_id}"
                tasks_for_route = exclusive.get(route_id, [])[:3]
                label = route_labels.get(route_id, route_id)
                if tasks_for_route:
                    sub = pick_i18n(tasks_for_route[0]["title"], lang)
                    label = f"{label} → {sub}"

                lane = reserve_lane(layer, ri)
                add_node({
                    "id": preview_id,
                    "node_type": "branch_path",
                    "task_id": tasks_for_route[0]["id"] if tasks_for_route else None,
                    "choice_id": route_id,
                    "branch_id": "housing_route",
                    "label": label,
                    "state": "selected_path" if selected else "alternative",
                    "phase_id": "phase_pre_arrival",
                    "branch_parent": None,
                    "meta": {"selected": selected, "route_id": route_id},
                })
                place(preview_id, layer, lane)
                add_edge(fork_id, preview_id, "branch", selected)
                choice_lanes.append((preview_id, lane, route_id))

            merge_layer = layer + 1
            merge_id = "merge_housing_route"
            mlane = reserve_lane(merge_layer, 0)
            add_node({
                "id": merge_id,
                "node_type": "merge",
                "label": "",
                "state": "completed",
                "phase_id": "phase_pre_arrival",
            })
            place(merge_id, merge_layer, mlane)
            for pid, pl, _ in choice_lanes:
                add_edge(pid, merge_id, "merge", True)
            prev_exit = (merge_id, mlane)
            layer = merge_layer + 1

        # Main task node
        state = get_task_state_with_branches(task["id"], profile, completed_set, branch_choices, roadmap)
        loc = _localize_task(task, state, profile, completed_set, lang)
        bp = get_branch_point_for_task(task["id"], profile, branch_choices, lang, roadmap)
        if bp:
            loc["branch_point"] = bp

        tlane = reserve_lane(layer, prev_exit[1] if prev_exit else 0)
        add_node({
            "id": task["id"],
            "node_type": "task",
            "task_id": task["id"],
            "label": loc["title"],
            "state": state,
            "phase_id": task["phase"],
            "branch_point": bp,
            "meta": loc,
        })
        place(task["id"], layer, tlane)
        connect_prev(task["id"], tlane)
        prev_exit = (task["id"], tlane)
        layer += 1

        if not bp or len(bp.get("choices") or []) < 2:
            continue

        fork_id = f"fork_{bp['id']}"
        flane = reserve_lane(layer, tlane)
        add_edge(task["id"], fork_id, "branch", True)
        add_node({
            "id": fork_id,
            "node_type": "fork",
            "task_id": task["id"],
            "label": (bp.get("prompt") or "")[:36],
            "state": "completed" if bp.get("selected") else "available",
            "phase_id": task["phase"],
            "branch_id": bp["id"],
            "meta": {"prompt": bp.get("prompt"), "selected": bp.get("selected")},
        })
        place(fork_id, layer, flane)
        layer += 1

        choices = bp["choices"]
        n = len(choices)
        path_exits: List[Tuple[str, int]] = []

        for ci, choice in enumerate(choices):
            selected = bp.get("selected") == choice["id"]
            preview_id = f"preview_{bp['id']}_{choice['id']}"
            unlock = choice.get("unlock_tasks") or []
            preview_title = choice.get("label", "")
            if unlock and unlock[0] in supp_map:
                preview_title = pick_i18n(supp_map[unlock[0]].get("title"), lang)

            pstate = "alternative"
            if selected:
                if unlock:
                    pstate = get_task_state_with_branches(
                        unlock[0], profile, completed_set, branch_choices, roadmap
                    )
                    if pstate == "skipped":
                        pstate = "selected_path"
                else:
                    pstate = "selected_path"

            plane = reserve_lane(layer, ci)
            add_node({
                "id": preview_id,
                "node_type": "branch_path",
                "task_id": unlock[0] if unlock else None,
                "choice_id": choice["id"],
                "branch_id": bp["id"],
                "label": preview_title,
                "state": pstate,
                "phase_id": task["phase"],
                "branch_parent": task["id"],
                "meta": {"choice": choice, "selected": selected, "description": choice.get("description")},
            })
            place(preview_id, layer, plane)
            add_edge(fork_id, preview_id, "branch", selected)

            exit_id = preview_id
            exit_lane = plane

            if selected and unlock:
                for utid in unlock:
                    if utid not in supp_map or utid in node_ids:
                        continue
                    stask = supp_map[utid]
                    sstate = get_task_state_with_branches(
                        utid, profile, completed_set, branch_choices, roadmap
                    )
                    if sstate == "skipped":
                        continue
                    sloc = localize_supplemental_task(
                        stask, sstate, profile, completed_set, lang, branch_choices, roadmap
                    )
                    add_node({
                        "id": utid,
                        "node_type": "task",
                        "task_id": utid,
                        "label": sloc["title"],
                        "state": sstate,
                        "phase_id": stask["phase"],
                        "branch_parent": task["id"],
                        "meta": sloc,
                    })
                    ulane = reserve_lane(layer + 1, plane)
                    place(utid, layer + 1, ulane)
                    add_edge(preview_id, utid, "flow", True)
                    exit_id = utid
                    exit_lane = ulane

            path_exits.append((exit_id, exit_lane))

        child_layer = layer + 1
        merge_layer = child_layer + 1
        if all(e[0].startswith("preview_") for e, _ in zip(path_exits, choices)):
            merge_layer = layer + 1

        merge_id = f"merge_{bp['id']}"
        mlane = reserve_lane(merge_layer, tlane)
        add_node({
            "id": merge_id,
            "node_type": "merge",
            "label": "",
            "state": "completed",
            "phase_id": task["phase"],
        })
        place(merge_id, merge_layer, mlane)
        for exit_id, el in path_exits:
            add_edge(exit_id, merge_id, "merge", True)
        prev_exit = (merge_id, mlane)
        layer = merge_layer + 1

    _layout_from_layers(graph_nodes, phases)
    _filter_edges(graph_edges, node_ids)

    return {
        "nodes": graph_nodes,
        "edges": graph_edges,
        "phases": [{"id": p["id"], "order": p["order"], "title": phase_title[p["id"]]} for p in phases],
        "dimensions": _graph_dimensions(graph_nodes),
    }


def _filter_edges(edges: List[Dict[str, Any]], node_ids: Set[str]) -> None:
    valid = []
    for e in edges:
        if e["from"] in node_ids and e["to"] in node_ids:
            valid.append(e)
    edges.clear()
    edges.extend(valid)


def _layout_from_layers(nodes: List[Dict[str, Any]], phases: List[Dict]) -> None:
    if not nodes:
        return

    for n in nodes:
        layer = n.get("layer", 0)
        lane = n.get("lane", 0)
        n["x"] = PAD_X + layer * LAYER_W
        n["y"] = PAD_Y + HEADER_H + lane * LANE_H
        n["column"] = n.get("phase_id", "")


def _graph_dimensions(nodes: List[Dict[str, Any]]) -> Dict[str, int]:
    if not nodes:
        return {"width": 800, "height": 400}
    max_x = max(n.get("x", 0) for n in nodes) + NODE_W + PAD_X + 40
    min_y = min(n.get("y", 0) for n in nodes)
    max_y = max(n.get("y", 0) for n in nodes) + NODE_H + PAD_Y
    height = max(360, max_y - min(min_y, PAD_Y) + PAD_Y + 56)
    return {"width": max(720, max_x), "height": height}
