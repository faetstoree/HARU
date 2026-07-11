"""Gemini chat tools: maps search and interactive user questions."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from google.genai import types

from maps_engine import build_map_block, infer_maps_query, looks_like_location_query
from roadmap_mermaid_engine import (
    build_mermaid_block,
    build_roadmap_mermaid_block,
    looks_like_roadmap_query,
)
from backend_i18n import t


def chat_function_declarations() -> List[types.FunctionDeclaration]:
    return [
        types.FunctionDeclaration(
            name="search_maps_place",
            description=(
                "Search Google Maps for a place and show an interactive map in chat. "
                "Use when the student asks where something is, how to get there, or wants "
                "the nearest facility (ward office, bank, phone shop, immigration, etc.)."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "query": types.Schema(
                        type="STRING",
                        description="Search query, e.g. ward office near Shinjuku",
                    ),
                    "near": types.Schema(
                        type="STRING",
                        description="Optional area hint (ward, city, or address)",
                    ),
                    "label": types.Schema(
                        type="STRING",
                        description="Short map card title shown to the user",
                    ),
                },
                required=["query"],
            ),
        ),
        types.FunctionDeclaration(
            name="ask_user_question",
            description=(
                "Ask the student a clarifying multiple-choice question when you need more "
                "information before giving advice (housing type, document status, urgency, etc.)."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "question": types.Schema(type="STRING", description="Question text"),
                    "choices": types.Schema(
                        type="ARRAY",
                        items=types.Schema(
                            type="OBJECT",
                            properties={
                                "id": types.Schema(type="STRING"),
                                "label": types.Schema(type="STRING"),
                            },
                            required=["id", "label"],
                        ),
                        description="2-4 choices",
                    ),
                },
                required=["question", "choices"],
            ),
        ),
        types.FunctionDeclaration(
            name="show_roadmap_diagram",
            description=(
                "Show the student's personalized relocation roadmap as an interactive Mermaid "
                "flowchart in chat. Use when they ask about overall procedure flow, what comes "
                "next, phase overview, or want to see their roadmap visually."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "scope": types.Schema(
                        type="STRING",
                        description="next_steps | current_phase | full",
                    ),
                    "highlight_task_id": types.Schema(
                        type="STRING",
                        description="Optional task id to highlight (e.g. task_immigration)",
                    ),
                    "title": types.Schema(
                        type="STRING",
                        description="Short card title shown above the diagram",
                    ),
                },
            ),
        ),
        types.FunctionDeclaration(
            name="render_mermaid",
            description=(
                "Render a custom Mermaid diagram in chat to explain a process, timeline, or "
                "decision tree. Use valid Mermaid syntax (flowchart TD/LR, sequenceDiagram, etc.)."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "source": types.Schema(
                        type="STRING",
                        description="Mermaid diagram source (without markdown fences)",
                    ),
                    "title": types.Schema(
                        type="STRING",
                        description="Short title for the diagram card",
                    ),
                },
                required=["source"],
            ),
        ),
    ]


def build_chat_tools(*, include_search: bool = True) -> List[types.Tool]:
    """Build chat tools. Google Search must share one Tool proto with function declarations."""
    decls = chat_function_declarations()
    if include_search:
        return [
            types.Tool(
                google_search=types.GoogleSearch(),
                function_declarations=decls,
            )
        ]
    return [types.Tool(function_declarations=decls)]


def build_chat_generate_config(
    system_instruction: str,
    *,
    include_search: bool = True,
) -> types.GenerateContentConfig:
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=build_chat_tools(include_search=include_search),
    )
    if include_search:
        config.tool_config = types.ToolConfig(include_server_side_tool_invocations=True)
    return config


def _pick_lang(lang: str) -> str:
    return lang if lang in ("zh-TW", "en", "ja") else "en"


def build_ai_question_block(
    question: str,
    choices: List[Dict[str, str]],
    lang: str = "ja",
) -> Dict[str, Any]:
    lang_key = _pick_lang(lang)
    cleaned = []
    for i, c in enumerate(choices[:4]):
        cid = (c.get("id") or chr(ord("a") + i)).strip()
        label = (c.get("label") or "").strip()
        if label:
            cleaned.append({"id": cid, "label": label})
    if len(cleaned) < 2:
        cleaned = [
            {"id": "a", "label": t("yesLabel", lang_key)},
            {"id": "b", "label": t("noLabel", lang_key)},
        ]
    return {
        "type": "ai_question",
        "question": question,
        "choices": cleaned,
    }


def execute_chat_tool(
    name: str,
    args: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    lang = _pick_lang(context.get("lang", "en"))
    blocks: List[Dict[str, Any]] = []

    if name == "search_maps_place":
        query = (args.get("query") or "").strip()
        near = (args.get("near") or context.get("current_address") or "").strip()
        if near and near.lower() not in query.lower():
            query = f"{query} {near}".strip()
        label = (args.get("label") or query).strip()
        block = build_map_block(
            query,
            lang,
            latitude=context.get("latitude"),
            longitude=context.get("longitude"),
            label=label,
            api_key=context.get("maps_api_key"),
        )
        blocks.append(block)
        return {
            "summary": f"Map shown for: {query}",
            "blocks": blocks,
            "data": {"query": query, "embed_url": block["embed_url"]},
        }

    if name == "ask_user_question":
        question = (args.get("question") or "").strip()
        choices = args.get("choices") or []
        if not isinstance(choices, list):
            choices = []
        block = build_ai_question_block(question, choices, lang)
        blocks.append(block)
        return {
            "summary": "Question shown to user",
            "blocks": blocks,
            "data": {"question": question},
        }

    if name == "show_roadmap_diagram":
        scope = (args.get("scope") or "next_steps").strip()
        highlight = (args.get("highlight_task_id") or context.get("focus_task_id") or "").strip() or None
        title = (args.get("title") or "").strip() or None
        school_info = context.get("school_info") or {}
        completed = context.get("completed_tasks") or []
        branch_choices = context.get("branch_choices") or {}
        block = build_roadmap_mermaid_block(
            school_info,
            completed,
            lang,
            scope=scope,
            highlight_task_id=highlight,
            branch_choices=branch_choices,
            title=title,
        )
        blocks.append(block)
        return {
            "summary": f"Roadmap diagram shown ({scope})",
            "blocks": blocks,
            "data": {"scope": scope, "highlight_task_id": highlight},
        }

    if name == "render_mermaid":
        source = (args.get("source") or "").strip()
        title = (args.get("title") or "").strip() or None
        if not source:
            return {"summary": "Empty mermaid source", "blocks": [], "data": {}}
        block = build_mermaid_block(source, lang, title=title, diagram_kind="custom")
        blocks.append(block)
        return {
            "summary": "Mermaid diagram rendered",
            "blocks": blocks,
            "data": {"title": title or ""},
        }

    return {"summary": f"Unknown tool: {name}", "blocks": [], "data": {}}


def _part_function_call(part: Any) -> Any:
    fc = getattr(part, "function_call", None)
    if fc:
        return fc
    if isinstance(part, dict):
        return part.get("function_call") or part.get("functionCall")
    return None


def _function_call_args(raw_args: Any) -> Dict[str, Any]:
    if raw_args is None:
        return {}
    if isinstance(raw_args, dict):
        return raw_args
    if isinstance(raw_args, str):
        try:
            parsed = json.loads(raw_args)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    try:
        return dict(raw_args)
    except (TypeError, ValueError):
        return {}


def _extract_function_calls(response: Any) -> Tuple[List[Any], str]:
    calls: List[Any] = []
    texts: List[str] = []
    for cand in getattr(response, "candidates", None) or []:
        content = getattr(cand, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", None) or []:
            fc = _part_function_call(part)
            if fc:
                calls.append(fc)
            txt = getattr(part, "text", None)
            if txt:
                texts.append(txt)
    return calls, "".join(texts).strip()


def mock_tool_blocks(message: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Fallback tool-like blocks in mock mode."""
    blocks: List[Dict[str, Any]] = []
    if looks_like_location_query(message):
        query = infer_maps_query(
            message,
            near=context.get("current_address"),
            school_info=context.get("school_info"),
            current_address=context.get("current_address"),
            focus_task_id=context.get("focus_task_id"),
        )
        blocks.append(
            build_map_block(
                query,
                context.get("lang", "ja"),
                latitude=context.get("latitude"),
                longitude=context.get("longitude"),
                api_key=context.get("maps_api_key"),
            )
        )
    if looks_like_roadmap_query(message):
        blocks.append(
            build_roadmap_mermaid_block(
                context.get("school_info") or {},
                context.get("completed_tasks") or [],
                context.get("lang", "ja"),
                scope="next_steps",
                highlight_task_id=context.get("focus_task_id"),
                branch_choices=context.get("branch_choices") or {},
            )
        )
    return blocks


async def run_chat_with_tools(
    genai_client: Any,
    contents: List[types.Content],
    *,
    system_instruction: str,
    lang: str,
    context: Dict[str, Any],
    generate_fn: Any,
    max_rounds: int = 4,
) -> Tuple[str, List[Dict[str, Any]], bool]:
    """Run Gemini with function-calling loop. Returns (text, extra_blocks, used_search)."""
    tool_blocks: List[Dict[str, Any]] = []
    used_search = False
    final_text = ""
    working = list(contents)

    include_search = True

    for _ in range(max_rounds):
        config = build_chat_generate_config(system_instruction, include_search=include_search)
        try:
            response, _model, tools_used = await generate_fn(
                genai_client,
                contents=working,
                config=config,
            )
        except Exception as exc:
            msg = str(exc).upper()
            if include_search and any(
                marker in msg
                for marker in (
                    "INVALID_ARGUMENT",
                    "FAILED_PRECONDITION",
                    "TOOL USE WITH FUNCTION CALLING",
                    "FUNCTION CALLING",
                )
            ):
                include_search = False
                response, _model, tools_used = await generate_fn(
                    genai_client,
                    contents=working,
                    config=build_chat_generate_config(system_instruction, include_search=False),
                )
            else:
                raise
        used_search = used_search or (tools_used and include_search)
        fcalls, text = _extract_function_calls(response)

        if not fcalls:
            final_text = text
            break

        model_content = None
        if response.candidates:
            model_content = response.candidates[0].content
        if model_content:
            working.append(model_content)

        fr_parts: List[types.Part] = []
        for fc in fcalls:
            raw_args = _function_call_args(getattr(fc, "args", None))
            fc_name = getattr(fc, "name", None) or ""
            fc_id = getattr(fc, "id", None)
            result = execute_chat_tool(fc_name, raw_args, context)
            tool_blocks.extend(result.get("blocks") or [])
            fr_kwargs: Dict[str, Any] = {
                "name": fc_name or "tool",
                "response": {"summary": result.get("summary", "ok"), **(result.get("data") or {})},
            }
            if fc_id:
                fr_kwargs["id"] = fc_id
            fr_parts.append(types.Part.from_function_response(**fr_kwargs))
        working.append(types.Content(role="user", parts=fr_parts))
        final_text = text
    else:
        final_text = final_text or ""

    return final_text, tool_blocks, used_search
