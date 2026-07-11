"""Gemini API helpers ? model fallbacks and key verification."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from google import genai
from google.genai import types

from models_config import GEMINI_MODEL, GEMINI_MODEL_FALLBACKS

_RETRYABLE_MARKERS = (
    "403",
    "404",
    "PERMISSION_DENIED",
    "NOT_FOUND",
    "UNAVAILABLE",
    "FAILED_PRECONDITION",
    "INVALID_ARGUMENT",
)


def _config_without_google_search(
    config: types.GenerateContentConfig,
) -> Optional[types.GenerateContentConfig]:
    tools = getattr(config, "tools", None) or []
    if not tools:
        return None
    rebuilt: List[types.Tool] = []
    for tool in tools:
        decls = getattr(tool, "function_declarations", None)
        if decls:
            rebuilt.append(types.Tool(function_declarations=decls))
    if not rebuilt:
        return None
    return types.GenerateContentConfig(
        system_instruction=getattr(config, "system_instruction", None),
        max_output_tokens=getattr(config, "max_output_tokens", None),
        tools=rebuilt,
    )


def model_candidates() -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    primary = (os.getenv("GEMINI_MODEL") or GEMINI_MODEL).strip()
    for name in [primary, *GEMINI_MODEL_FALLBACKS]:
        if name and name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def _is_retryable(exc: Exception) -> bool:
    msg = str(exc).upper()
    return any(marker in msg for marker in _RETRYABLE_MARKERS)


def classify_gemini_error(exc: Exception) -> str:
    msg = str(exc).upper()
    if "PERMISSION_DENIED" in msg or "403" in msg:
        return "permission_denied"
    if "API_KEY_INVALID" in msg or "INVALID API KEY" in msg or "401" in msg:
        return "invalid_key"
    if "QUOTA" in msg or "429" in msg:
        return "quota"
    return "other"


async def generate_with_model_fallback(
    client: genai.Client,
    *,
    contents: Any,
    config: Optional[types.GenerateContentConfig] = None,
    models: Optional[List[str]] = None,
    strip_tools_on_retry: bool = True,
) -> Tuple[Any, str, bool]:
    """Try generate_content across models. Returns (response, model, tools_were_used)."""
    models_list = models or model_candidates()
    has_tools = bool(config is not None and getattr(config, "tools", None))
    last_exc: Optional[Exception] = None

    for model in models_list:
        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            return response, model, has_tools
        except Exception as exc:
            last_exc = exc
            if not _is_retryable(exc):
                break

    if strip_tools_on_retry and has_tools and config is not None:
        searchless = _config_without_google_search(config)
        if searchless is not None:
            for model in models_list:
                try:
                    response = await client.aio.models.generate_content(
                        model=model,
                        contents=contents,
                        config=searchless,
                    )
                    return response, model, True
                except Exception as exc:
                    last_exc = exc
                    if not _is_retryable(exc):
                        break

        bare_config = types.GenerateContentConfig(
            system_instruction=getattr(config, "system_instruction", None),
            max_output_tokens=getattr(config, "max_output_tokens", None),
        )
        for model in models_list:
            try:
                response = await client.aio.models.generate_content(
                    model=model,
                    contents=contents,
                    config=bare_config,
                )
                return response, model, False
            except Exception as exc:
                last_exc = exc
                if not _is_retryable(exc):
                    break

    if last_exc:
        raise last_exc
    raise RuntimeError("No Gemini models configured")


async def verify_gemini_key(key: str, lang: str = "en") -> Dict[str, Any]:
    """Ping Gemini with fallback models."""
    del lang  # reserved for future localized server messages
    client = genai.Client(api_key=key)
    last_exc: Optional[Exception] = None
    for model in model_candidates():
        try:
            await client.aio.models.generate_content(
                model=model,
                contents="Reply with OK only.",
                config=types.GenerateContentConfig(max_output_tokens=8),
            )
            return {
                "verified": True,
                "model": model,
                "error": None,
                "error_kind": None,
            }
        except Exception as exc:
            last_exc = exc
            if not _is_retryable(exc):
                break
    exc = last_exc or RuntimeError("Verification failed")
    return {
        "verified": False,
        "model": None,
        "error": str(exc),
        "error_kind": classify_gemini_error(exc),
    }
