"""Diagnose roadmap graph layout issues."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import defaultdict
from roadmap_engine import build_roadmap_response

NODE_W, NODE_H = 196, 64

si = {
    "housing_type": "dorm",
    "part_time_plan": "yes",
    "has_residence_card": True,
    "sim_at_airport": False,
}
r = build_roadmap_response(si, [], "ja", branch_choices={})
g = r["graph"]
nodes = g["nodes"]
edges = g["edges"]
dims = g["dimensions"]
issues = []


def box(n):
    w = 36 if n["node_type"] in ("fork", "merge") else NODE_W
    h = 36 if n["node_type"] in ("fork", "merge") else NODE_H
    return n["x"], n["y"], w, h


for i, a in enumerate(nodes):
    ax, ay, aw, ah = box(a)
    for b in nodes[i + 1 :]:
        bx, by, bw, bh = box(b)
        if not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay):
            issues.append(f"OVERLAP: {a['id']} vs {b['id']}")

legend_y = dims["height"] - 24
for n in nodes:
    _, y, _, h = box(n)
    if y + h > legend_y:
        issues.append(f"LEGEND_COLLISION: {n['id']}")

if dims["height"] > 520:
    issues.append(f"TALL_GRAPH: {dims['height']}px")

print("dims", dims)
print("nodes", len(nodes), "edges", len(edges))
print("types", {t: sum(1 for n in nodes if n["node_type"] == t) for t in sorted(set(n["node_type"] for n in nodes))})
print("issues", len(issues))
for i in issues[:20]:
    print(" -", i)
