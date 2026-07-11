"""4-choice diagnostic quiz for chat (max 6 questions per session)."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

from roadmap_engine import get_next_tasks, normalize_lang, pick_i18n, profile_from_dict
from task_id_aliases import expand_task_id_set, task_ids_overlap
from backend_i18n import t

QUIZ_PATH = os.path.join(os.path.dirname(__file__), "data", "quiz_questions.json")
MAX_QUESTIONS = 6


@lru_cache(maxsize=1)
def load_quiz_bank() -> Dict[str, Any]:
    with open(QUIZ_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _localize_question(q: Dict[str, Any], lang: str) -> Dict[str, Any]:
    lang = normalize_lang(lang)
    choices = []
    for c in q.get("choices", [])[:4]:
        choices.append({
            "id": c["id"],
            "label": pick_i18n(c.get("label", {}), lang),
        })
    return {
        "question_id": q["id"],
        "prompt": pick_i18n(q.get("prompt", {}), lang),
        "choices": choices,
        "question_index": 0,
        "total": 0,
    }


def _score_questions(
    focus_task_id: Optional[str],
    school_info: Dict[str, Any],
    completed_tasks: List[str],
    lang: str,
) -> List[Dict[str, Any]]:
    bank = load_quiz_bank().get("questions", [])
    completed_set = set(completed_tasks)
    for tid in list(completed_set):
        completed_set.update(expand_task_id_set(tid))
    scored = []
    for q in bank:
        score = q.get("priority", 0)
        task_ids = q.get("task_ids") or []
        if focus_task_id and task_ids_overlap(focus_task_id, task_ids):
            score += 20
        skip_if = q.get("skip_if_task_completed")
        if skip_if and skip_if in completed_set:
            continue
        only_if = q.get("only_if_not_completed")
        if only_if and only_if in completed_set:
            continue
        scored.append((score, q))
    scored.sort(key=lambda x: -x[0])
    seen = set()
    ordered = []
    for _, q in scored:
        if q["id"] in seen:
            continue
        seen.add(q["id"])
        ordered.append(q)
    return ordered[:MAX_QUESTIONS]


def start_quiz_session(
    school_info: Dict[str, Any],
    completed_tasks: List[str],
    lang: str = "zh-TW",
    focus_task_id: Optional[str] = None,
) -> Dict[str, Any]:
    lang = normalize_lang(lang)
    profile = profile_from_dict(school_info)
    if not focus_task_id:
        next_tasks = get_next_tasks(profile, completed_tasks, limit=1, lang=lang)
        focus_task_id = next_tasks[0]["id"] if next_tasks else None

    selected = _score_questions(focus_task_id, school_info, completed_tasks, lang)
    if not selected:
        intro = t("quizNoQuestions", lang)
        return {
            "quiz_state": {"active": False},
            "done": True,
            "message_blocks": [{"type": "text", "content": intro}],
        }

    question_ids = [q["id"] for q in selected]
    quiz_state = {
        "active": True,
        "focus_task_id": focus_task_id,
        "question_index": 0,
        "answers": [],
        "question_ids": question_ids,
        "max_questions": min(len(question_ids), MAX_QUESTIONS),
    }
    q_block = build_quiz_question_block(selected[0], 0, quiz_state["max_questions"], lang)
    intro = t("quizIntro", lang, n=quiz_state["max_questions"])
    return {
        "quiz_state": quiz_state,
        "done": False,
        "message_blocks": [
            {"type": "text", "content": intro},
            q_block,
        ],
    }


def build_quiz_question_block(
    q: Dict[str, Any],
    index: int,
    total: int,
    lang: str,
) -> Dict[str, Any]:
    loc = _localize_question(q, lang)
    loc["question_index"] = index + 1
    loc["total"] = total
    return {"type": "quiz_question", **loc}


def submit_quiz_answer(
    quiz_state: Dict[str, Any],
    choice_id: str,
    school_info: Dict[str, Any],
    completed_tasks: List[str],
    lang: str = "zh-TW",
) -> Dict[str, Any]:
    lang = normalize_lang(lang)
    if not quiz_state.get("active"):
        return {"quiz_state": quiz_state, "done": True, "message_blocks": []}

    bank = {q["id"]: q for q in load_quiz_bank().get("questions", [])}
    q_ids = quiz_state.get("question_ids", [])
    idx = quiz_state.get("question_index", 0)
    if idx >= len(q_ids):
        return _finish_quiz(quiz_state, bank, school_info, completed_tasks, lang)

    qid = q_ids[idx]
    q = bank.get(qid)
    if not q:
        quiz_state["question_index"] = idx + 1
        return _next_or_finish(quiz_state, bank, school_info, completed_tasks, lang)

    choice = next((c for c in q.get("choices", []) if c["id"] == choice_id), None)
    quiz_state.setdefault("answers", []).append({
        "question_id": qid,
        "choice_id": choice_id,
        "choice_label": pick_i18n(choice.get("label", {}), lang) if choice else choice_id,
    })
    quiz_state["question_index"] = idx + 1

    if quiz_state["question_index"] >= quiz_state.get("max_questions", MAX_QUESTIONS) or quiz_state["question_index"] >= len(q_ids):
        return _finish_quiz(quiz_state, bank, school_info, completed_tasks, lang)

    return _next_or_finish(quiz_state, bank, school_info, completed_tasks, lang)


def _next_or_finish(
    quiz_state: Dict[str, Any],
    bank: Dict[str, Dict],
    school_info: Dict[str, Any],
    completed_tasks: List[str],
    lang: str,
) -> Dict[str, Any]:
    idx = quiz_state["question_index"]
    q_ids = quiz_state["question_ids"]
    if idx >= len(q_ids) or idx >= quiz_state.get("max_questions", MAX_QUESTIONS):
        return _finish_quiz(quiz_state, bank, school_info, completed_tasks, lang)
    q = bank[q_ids[idx]]
    block = build_quiz_question_block(q, idx, quiz_state["max_questions"], lang)
    return {
        "quiz_state": quiz_state,
        "done": False,
        "message_blocks": [block],
    }


def _finish_quiz(
    quiz_state: Dict[str, Any],
    bank: Dict[str, Dict],
    school_info: Dict[str, Any],
    completed_tasks: List[str],
    lang: str,
) -> Dict[str, Any]:
    lang = normalize_lang(lang)
    quiz_state["active"] = False
    lines = []
    recommendations = []
    suggested_task_ids = []

    for ans in quiz_state.get("answers", []):
        q = bank.get(ans["question_id"])
        if not q:
            continue
        choice = next((c for c in q.get("choices", []) if c["id"] == ans["choice_id"]), None)
        if not choice:
            continue
        if choice.get("recommendation"):
            recommendations.append(pick_i18n(choice["recommendation"], lang))
        if choice.get("suggest_task"):
            suggested_task_ids.append(choice["suggest_task"])

    header = t("quizDoneHeader", lang)
    lines.append(header)
    if recommendations:
        for i, rec in enumerate(recommendations[:6], 1):
            lines.append(f"{i}. {rec}")
    else:
        lines.append(t("quizDoneDefault", lang))

    focus = quiz_state.get("focus_task_id")
    if focus and focus not in completed_tasks:
        lines.append(t("quizDonePriority", lang, focus=focus))

    return {
        "quiz_state": quiz_state,
        "done": True,
        "suggested_task_ids": list(dict.fromkeys(suggested_task_ids)),
        "message_blocks": [{"type": "text", "content": "\n".join(lines)}],
    }
