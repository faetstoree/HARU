# -*- coding: utf-8 -*-
"""Verify AI data linkage and smoke-test API endpoints."""
from __future__ import annotations

import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient  # noqa: E402

SCHOOL = {
    "school_name": "Test Language School",
    "arrival_date": "2026-04-01",
    "location": "\u65b0\u5bbf\u533a",
    "japanese_level": "N4",
    "has_residence_card": True,
    "housing_type": "dorm",
    "school_type": "language_school",
    "part_time_plan": "no",
    "sim_at_airport": False,
    "already_exchanged": False,
}


def audit_task_refs() -> dict:
    roadmap = json.load(open(os.path.join(ROOT, "data", "roadmap.json"), encoding="utf-8"))
    branches = json.load(open(os.path.join(ROOT, "data", "roadmap_branches.json"), encoding="utf-8"))
    valid = {t["id"] for t in roadmap["tasks"]} | {t["id"] for t in branches.get("branch_tasks", [])}
    refs: set[str] = set()

    quiz = json.load(open(os.path.join(ROOT, "data", "quiz_questions.json"), encoding="utf-8"))
    for q in quiz.get("questions", []):
        refs.update(q.get("task_ids", []))
        if q.get("skip_if_task_completed"):
            refs.add(q["skip_if_task_completed"])
        for c in q.get("choices", []):
            if c.get("suggest_task"):
                refs.add(c["suggest_task"])

    for path, key in [
        (os.path.join(ROOT, "data", "knowledge", "articles.json"), "articles"),
        (os.path.join(ROOT, "data", "knowledge", "service_guides.json"), "guides"),
        (os.path.join(ROOT, "data", "official_resources.json"), "resources"),
    ]:
        data = json.load(open(path, encoding="utf-8"))
        for item in data.get(key, []):
            refs.update(item.get("task_ids", []))

    stale = sorted(refs - valid)
    return {"valid_count": len(valid), "ref_count": len(refs), "stale": stale}


def run_api_smoke() -> list[dict]:
    from main import app

    client = TestClient(app)
    device_id = "ai_verify_device"
    results = []

    def record(name: str, resp):
        ok = resp.status_code == 200
        body = {}
        if resp.headers.get("content-type", "").startswith("application/json"):
            body = resp.json()
            ok = ok and body.get("status") in ("success", None)
        elif resp.status_code == 200 and name == "pdf":
            ok = resp.headers.get("content-type") == "application/pdf"
        results.append({"endpoint": name, "status": resp.status_code, "ok": ok})
        return body

    record("chat", client.post("/api/chat", json={
        "message": "\u4f4f\u6c11\u767b\u9332\u306f\u3069\u3046\u3059\u308c\u3070\u3044\u3044\uff1f",
        "school_info": SCHOOL,
        "chat_history": [],
        "lang": "ja",
        "completed_tasks": [],
        "device_id": device_id,
    }))

    chat_resp = client.post("/api/chat", json={
        "message": "test",
        "school_info": SCHOOL,
        "chat_history": [],
        "lang": "ja",
        "completed_tasks": [],
        "device_id": device_id,
        "focus_task_id": "task_ward_office",
    })
    blocks = chat_resp.json().get("message", {}).get("blocks", [])
    results.append({
        "endpoint": "chat-blocks",
        "status": chat_resp.status_code,
        "ok": chat_resp.status_code == 200 and len(blocks) >= 2,
        "block_types": [b.get("type") for b in blocks],
    })

    record("agent-step", client.post("/api/agent-step", json={
        "school_info": SCHOOL,
        "completed_tasks": [],
        "current_address": "\u65b0\u5bbf\u533a",
        "latitude": 35.69,
        "longitude": 139.70,
        "local_time": "2026-07-10T10:00",
        "day_of_week": "Friday",
        "lang": "ja",
        "device_id": device_id,
    }))
    record("agent-step-problem", client.post("/api/agent-step", json={
        "school_info": SCHOOL,
        "completed_tasks": [],
        "current_address": "\u65b0\u5bbf\u533a",
        "latitude": 35.69,
        "longitude": 139.70,
        "local_time": "2026-07-10T10:00",
        "day_of_week": "Friday",
        "lang": "ja",
        "device_id": device_id,
        "problem_report": "\u533a\u5f79\u6240\u304c\u308f\u304b\u3089\u306a\u3044",
        "force_llm": True,
    }))
    record("personalize", client.post("/api/roadmap/task/personalize", json={
        "task_id": "task_ward_office",
        "school_info": SCHOOL,
        "completed_tasks": [],
        "branch_choices": {},
        "lang": "ja",
        "device_id": device_id,
    }))
    record("expand", client.post("/api/roadmap/task/expand", json={
        "task_id": "task_ward_office",
        "school_info": SCHOOL,
        "branch_choices": {},
        "lang": "ja",
    }))
    record("quiz-start", client.post("/api/quiz/start", json={
        "school_info": SCHOOL,
        "completed_tasks": [],
        "lang": "ja",
        "focus_task_id": "task_ward_office",
    }))
    record("tts", client.post("/api/tts", json={"text": "test", "lang": "ja"}))
    record("pdf", client.post("/api/export/roadmap-pdf", json={
        "school_info": SCHOOL,
        "completed_tasks": [],
        "lang": "ja",
        "device_id": device_id,
    }))

    return results


async def optional_live_gemini() -> dict:
    key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        return {"skipped": True, "reason": "GEMINI_API_KEY not set"}
    from gemini_engine import verify_gemini_key

    return await verify_gemini_key(key, "ja")


def main() -> None:
    audit = audit_task_refs()
    print("=== Task ID audit ===")
    print(f"Valid tasks: {audit['valid_count']}, unique refs: {audit['ref_count']}")
    if audit["stale"]:
        print("STALE:", audit["stale"])
        sys.exit(1)
    print("All task refs valid.")

    print("\n=== API smoke tests ===")
    failed = False
    for r in run_api_smoke():
        flag = "OK" if r.get("ok") else "FAIL"
        if not r.get("ok"):
            failed = True
        extra = ""
        if r.get("block_types"):
            extra = f" types={r['block_types']}"
        print(f"  [{flag}] {r['endpoint']} -> {r['status']}{extra}")

    print("\n=== Live Gemini (optional) ===")
    live = asyncio.run(optional_live_gemini())
    if live.get("skipped"):
        print(f"Skipped: {live['reason']}")
    else:
        print(live)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
