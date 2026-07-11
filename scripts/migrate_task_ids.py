"""One-shot migration: replace legacy task_ids in JSON data files with v3 ids."""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from task_id_aliases import migrate_task_id_list, TASK_ID_ALIASES  # noqa: E402

DATA_FILES = [
    os.path.join(ROOT, "data", "quiz_questions.json"),
    os.path.join(ROOT, "data", "official_resources.json"),
    os.path.join(ROOT, "data", "knowledge", "articles.json"),
    os.path.join(ROOT, "data", "knowledge", "service_guides.json"),
]

ARTICLE_ID_RENAMES = {
    "kb_task_address": "kb_task_ward_office",
}


def _migrate_quiz(data: dict) -> None:
    for q in data.get("questions", []):
        q["task_ids"] = migrate_task_id_list(q.get("task_ids", []))
        if q.get("skip_if_task_completed"):
            q["skip_if_task_completed"] = migrate_task_id_list(
                [q["skip_if_task_completed"]]
            )[0]
        for choice in q.get("choices", []):
            if choice.get("suggest_task"):
                choice["suggest_task"] = migrate_task_id_list([choice["suggest_task"]])[0]


def _migrate_resources(data: dict) -> None:
    for res in data.get("resources", []):
        res["task_ids"] = migrate_task_id_list(res.get("task_ids", []))


def _migrate_articles(data: dict) -> None:
    for art in data.get("articles", []):
        if art.get("id") in ARTICLE_ID_RENAMES:
            art["id"] = ARTICLE_ID_RENAMES[art["id"]]
        art["task_ids"] = migrate_task_id_list(art.get("task_ids", []))


def _migrate_guides(data: dict) -> None:
    for g in data.get("guides", []):
        g["task_ids"] = migrate_task_id_list(g.get("task_ids", []))


def main() -> None:
    handlers = {
        "quiz_questions.json": _migrate_quiz,
        "official_resources.json": _migrate_resources,
        "articles.json": _migrate_articles,
        "service_guides.json": _migrate_guides,
    }
    for path in DATA_FILES:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        name = os.path.basename(path)
        handlers[name](data)
        data["version"] = data.get("version", "1.0")
        if name == "official_resources.json":
            data["version"] = "2.0"
        elif name == "quiz_questions.json":
            data["version"] = "2.0"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Migrated {path}")
    print(f"Alias map covers {len(TASK_ID_ALIASES)} legacy ids")


if __name__ == "__main__":
    main()
