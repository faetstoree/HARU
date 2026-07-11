import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

_APP_ROOT = Path(__file__).resolve().parent
load_dotenv(dotenv_path=_APP_ROOT / ".env")
USE_MOCK_API = os.getenv("USE_MOCK_API", "false").lower() == "true"
TTS_ENABLED = os.getenv("TTS_ENABLED", "true").lower() == "true"
STT_ENABLED = os.getenv("STT_ENABLED", "true").lower() == "true"

MOCK_RESPONSES = {}
if os.path.exists("mock_responses.json"):
    try:
        with open("mock_responses.json", "r", encoding="utf-8") as f:
            MOCK_RESPONSES = json.load(f)
    except Exception as e:
        print(f"Error loading mock_responses.json: {e}")

def get_mock_response(lang: str, key: str, default_val: Any = None) -> Any:
    norm_lang = "en"
    if lang:
        lang_lower = lang.lower()
        if "zh" in lang_lower:
            norm_lang = "zh-TW"
        elif "ja" in lang_lower:
            norm_lang = "ja"
        elif "en" in lang_lower:
            norm_lang = "en"
    lang_data = MOCK_RESPONSES.get(norm_lang, MOCK_RESPONSES.get("en", {}))
    return lang_data.get(key, default_val)


from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from google import genai
from google.genai import types
from fastapi import Depends
from firestore_db import FirestoreDB, get_db
from roadmap_engine import (
    build_roadmap_response,
    get_all_task_ids_for_onboarding,
    merge_effective_completed,
    profile_from_dict,
    get_next_tasks,
    pick_i18n,
    load_roadmap,
)
from resource_engine import enrich_roadmap_with_official_links, resolve_resources_for_task, build_context_suggested_chips
from chat_blocks import merge_chat_blocks, parse_llm_text_or_json, message_to_history_text
from agent_engine import build_rule_based_decision, should_use_llm_for_agent
from roadmap_export import build_action_plan_pdf
from action_plan_builder import build_action_plan_content
from school_engine import search_schools
from knowledge_engine import (
    build_kb_context_for_llm,
    get_guide,
    get_knowledge_bundle_for_task,
    resolve_guides_for_task,
)
from roadmap_detail_engine import (
    build_mock_personalized_plan,
    build_personalize_prompt,
    get_static_task_expansion,
)
from roadmap_branch_engine import load_branches
from quiz_engine import start_quiz_session, submit_quiz_answer
from quiz_ai import synthesize_quiz_diagnosis
from action_plan_ai import enrich_action_plan_with_ai
from chat_tools import mock_tool_blocks, run_chat_with_tools
from gemini_engine import generate_with_model_fallback, verify_gemini_key
from models_config import GEMINI_MODEL, TTS_VOICES, STT_LANGUAGE_CODES, STT_SAMPLE_RATE_HZ
from roadmap_ai_engine import generate_ai_roadmap, merge_ai_overlay_into_roadmap
from backend_i18n import t as bi18n
from fastapi.responses import Response
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
from zoneinfo import ZoneInfo
import asyncio
import base64
from google.cloud import texttospeech
from google.cloud import speech

def _apply_school_info_to_user(user: Dict[str, Any], school_info: Dict[str, Any]) -> Dict[str, Any]:
    """Merge school_info into a user dict and return it."""
    user["school_name"] = school_info.get("school_name")
    user["arrival_date"] = school_info.get("arrival_date")
    user["location"] = school_info.get("location")
    user["japanese_level"] = school_info.get("japanese_level")
    user["has_residence_card"] = school_info.get("has_residence_card", True)
    user["housing_type"] = school_info.get("housing_type", "dorm")
    user["school_type"] = school_info.get("school_type", "language_school")
    user["part_time_plan"] = school_info.get("part_time_plan", "no")
    user["sim_at_airport"] = school_info.get("sim_at_airport", False)
    user["already_exchanged"] = school_info.get("already_exchanged", False)
    user["permit_obtained"] = school_info.get("permit_obtained", False)
    return user

def _school_info_from_user(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "school_name": user.get("school_name"),
        "arrival_date": user.get("arrival_date"),
        "location": user.get("location"),
        "japanese_level": user.get("japanese_level"),
        "has_residence_card": user.get("has_residence_card", True),
        "housing_type": user.get("housing_type") or "dorm",
        "school_type": user.get("school_type") or "language_school",
        "part_time_plan": user.get("part_time_plan") or "no",
        "sim_at_airport": bool(user.get("sim_at_airport", False)),
        "already_exchanged": bool(user.get("already_exchanged", False)),
        "permit_obtained": bool(user.get("permit_obtained", False)),
    }

def _roadmap_with_links(profile, completed, lang, school_info, branch_choices=None):
    roadmap = build_roadmap_response(profile, completed, lang, branch_choices=branch_choices or {})
    return enrich_roadmap_with_official_links(roadmap, school_info, lang)

app = FastAPI(title="留日主動式時間與搜尋感知 AI 伴侶 Haru")

# scheduler = AsyncIOScheduler()

@app.on_event("startup")
async def start_scheduler():
    pass
    # scheduler.add_job(background_decision_task, IntervalTrigger(minutes=2))
    # scheduler.start()

@app.on_event("shutdown")
async def stop_scheduler():
    pass
    # scheduler.shutdown()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

MODEL_NAME = GEMINI_MODEL
_genai_client_cache: Dict[str, Any] = {}


def _env_api_key() -> Optional[str]:
    return (os.getenv("GEMINI_API_KEY") or "").strip() or None


def _invalidate_genai_cache(key: Optional[str] = None):
    if key:
        _genai_client_cache.pop(key, None)
    else:
        _genai_client_cache.clear()


def _mask_api_key(key: str) -> str:
    key = (key or "").strip()
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}…{key[-4:]}"


def _env_maps_key() -> Optional[str]:
    return (os.getenv("GOOGLE_MAPS_API_KEY") or "").strip() or None


def _resolve_maps_key(db: Optional[FirestoreDB], device_id: Optional[str]) -> Optional[str]:
    # NOTE: async version used in handlers; this sync wrapper is kept for non-async callers
    if device_id and db is not None:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Inside async context — callers should use await directly
                return _env_maps_key()
            user = loop.run_until_complete(db.get_user(device_id))
        except Exception:
            user = None
        if user and user.get("google_maps_api_key"):
            return user["google_maps_api_key"].strip()
    return _env_maps_key()


async def _resolve_maps_key_async(db: Optional[FirestoreDB], device_id: Optional[str]) -> Optional[str]:
    if device_id and db is not None:
        user = await db.get_user(device_id)
        if user and user.get("google_maps_api_key"):
            return user["google_maps_api_key"].strip()
    return _env_maps_key()


def _gcp_credentials_available() -> bool:
    cred_path = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if not cred_path:
        return False
    return os.path.isfile(cred_path)


def _should_use_mock_tts() -> bool:
    if USE_MOCK_API:
        return True
    if not TTS_ENABLED:
        return True
    return not _gcp_credentials_available()


def _should_use_mock_stt() -> bool:
    if USE_MOCK_API:
        return True
    if not STT_ENABLED:
        return True
    return not _gcp_credentials_available()


async def _resolve_api_key_async(db: Optional[FirestoreDB], device_id: Optional[str]) -> Optional[str]:
    """Resolve API key per request: device DB → env (re-read each time)."""
    if device_id and db is not None:
        user = await db.get_user(device_id)
        if user and user.get("gemini_api_key"):
            return user["gemini_api_key"].strip()
    return _env_api_key()


def _resolve_api_key(db: Optional[FirestoreDB], device_id: Optional[str]) -> Optional[str]:
    """Sync wrapper — only safe outside of running event loop (e.g. startup checks)."""
    return _env_api_key()


def should_use_mock(db: Optional[FirestoreDB] = None, device_id: Optional[str] = None) -> bool:
    """Mock only when USE_MOCK_API=true AND no real API key is available (env check only; use async version in handlers)."""
    if not USE_MOCK_API:
        return False
    return not bool(_env_api_key())


async def should_use_mock_async(db: Optional[FirestoreDB] = None, device_id: Optional[str] = None) -> bool:
    if not USE_MOCK_API:
        return False
    return not bool(await _resolve_api_key_async(db, device_id))


async def get_genai_client_async(db: Optional[FirestoreDB] = None, device_id: Optional[str] = None):
    key = await _resolve_api_key_async(db, device_id)
    if not key:
        return None
    if key not in _genai_client_cache:
        _genai_client_cache[key] = genai.Client(api_key=key)
    return _genai_client_cache[key]


# Keep sync alias for non-async callers (uses env key only)
def get_genai_client(db=None, device_id=None):
    key = _env_api_key()
    if not key:
        return None
    if key not in _genai_client_cache:
        _genai_client_cache[key] = genai.Client(api_key=key)
    return _genai_client_cache[key]


async def require_genai_client_async(db: Optional[FirestoreDB] = None, device_id: Optional[str] = None):
    client = await get_genai_client_async(db, device_id)
    if not client:
        raise HTTPException(
            status_code=503,
            detail="Gemini API key is not configured. Set it in Profile settings (no server restart needed) or GEMINI_API_KEY in .env.",
        )
    return client


def require_genai_client(db=None, device_id=None):
    client = get_genai_client(db, device_id)
    if not client:
        raise HTTPException(
            status_code=503,
            detail="Gemini API key is not configured. Set it in Profile settings (no server restart needed) or GEMINI_API_KEY in .env.",
        )
    return client


if USE_MOCK_API:
    print("Mock API fallback ON - uses real Gemini when an API key is configured in Profile.")
elif _env_api_key():
    print("Gemini: GEMINI_API_KEY found in environment (also supports per-device keys in Profile).")
else:
    print("Gemini: no env key at boot — set API key in Profile settings (no restart required).")

LANG_MAP = {
    "zh-TW": "Traditional Chinese (繁體中文)",
    "en": "English",
    "ja": "Japanese (日本語)"
}

# 移除了所有寫死的營業時間，改為搜尋驅動策略 [SYSTEM]
SYSTEM_INSTRUCTION_BASE = """
You are "Haru", an extremely smart, context-aware AI Mentor for newly arrived international students in Japan.
Your distinguishing feature is that you have TEMPORAL AWARENESS (time/day) and strict DEPENDENCY LOGIC.

Crucial Instructions on Your Identity:
- Name Rule: Your name is strictly "Haru". Do NOT translate it into Japanese (like ハル) or Chinese (like 春) regardless of the output language.

Crucial Instruction on Operating Hours:
- Do NOT assume static business hours for any Japanese facilities. 
- You MUST actively use the Google Search tool to look up the actual operating hours of the nearest ward office (区役所/市役所), banks (ゆうちょ銀行 etc.), and mobile stores based on the student's current address or location.
- Always check if today is a public holiday in Japan if relevant to office closures.

[Strict Step Dependencies]
- Step 1: Address Registration (住民登録) at the Ward Office. (Requires: Passport, Residence Card). 
  * Note: If the student did NOT receive their Residence Card at the airport, they MUST get it issued at the Ward Office while registering their address. Make sure to explicitly tell them this.
- Step 2: National Health Insurance & Pension (国民健康保険・国民年金). Usually done at the Ward Office right after Address Registration.
- Step 3: Get a Mobile Number (SIM card). (Requires: Registered Address/Residence Card). You cannot get a normal phone plan without a registered address.
- Step 4: Open a Bank Account. (Requires: Registered Address, Mobile Phone Number, Passport, Hanko/Stamp). You CANNOT open a bank account without a Japanese mobile number.
- Step 5: School integration/entrance ceremonies.

[Proactive Action & Temporal Search Strategy]
1. Identify the student's target task based on completed steps.
2. Identify their current location / address (e.g., from their GPS data or target location).
3. Use Google Search to look up the actual local landmarks, nearest branches, and their actual business hours for today.
4. Compare these retrieved hours with the student's current local time and day. 
5. If the target place is closed, closing very soon, or it is currently late at night, proactively advise them to prepare documents, rest, or use online alternatives, rather than telling them to go there now.
6. Always remain encouraging and empathetic to the struggles of moving to a new country.
"""

class AgentStepRequest(BaseModel):
    school_info: Dict[str, Any]
    completed_tasks: List[str]
    current_address: Optional[str] = "Unknown"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    local_time: str      # 當前瀏覽器本地時間
    day_of_week: str     # 例如 "Tuesday"
    lang: str = "en"
    device_id: Optional[str] = None
    problem_report: Optional[str] = None
    task_action: Optional[str] = None
    force_llm: bool = False

class RoadmapExportRequest(BaseModel):
    device_id: str
    school_info: Dict[str, Any]
    completed_tasks: List[str]
    lang: str = "en"
    current_address: Optional[str] = None

class UserInitRequest(BaseModel):
    device_id: str
    school_info: Dict[str, Any]
    completed_tasks: List[str]

class UserProfileRequest(BaseModel):
    device_id: str
    school_info: Dict[str, Any]

class TaskCompleteRequest(BaseModel):
    device_id: str
    task_id: str
    lang: str = "en"
    branch_choices: Optional[Dict[str, str]] = None

class RoadmapRequest(BaseModel):
    device_id: str
    school_info: Optional[Dict[str, Any]] = None
    completed_tasks: Optional[List[str]] = None
    lang: str = "en"
    branch_choices: Optional[Dict[str, str]] = None

class BranchSelectRequest(BaseModel):
    device_id: str
    branch_id: str
    choice_id: str
    branch_choices: Dict[str, str] = {}
    school_info: Optional[Dict[str, Any]] = None
    completed_tasks: Optional[List[str]] = None
    lang: str = "en"

class TaskExpandRequest(BaseModel):
    task_id: str
    school_info: Dict[str, Any]
    branch_choices: Dict[str, str] = {}
    lang: str = "en"

class TaskPersonalizeRequest(BaseModel):
    task_id: str
    school_info: Dict[str, Any]
    completed_tasks: List[str] = []
    branch_choices: Dict[str, str] = {}
    lang: str = "en"
    current_address: Optional[str] = None
    device_id: Optional[str] = None

class ApiKeySaveRequest(BaseModel):
    device_id: str
    api_key: str
    lang: str = "en"

class ApiKeyTestRequest(BaseModel):
    device_id: str
    api_key: Optional[str] = None
    lang: str = "en"


class MapsKeySaveRequest(BaseModel):
    device_id: str
    api_key: str


class MapsKeyTestRequest(BaseModel):
    device_id: str
    api_key: Optional[str] = None


class ApiKeyClearRequest(BaseModel):
    device_id: str

class TaskSyncRequest(BaseModel):
    device_id: str
    completed_tasks: List[str]

class LocationUpdateRequest(BaseModel):
    device_id: str
    latitude: float
    longitude: float
    address: str

class AgentLatestRequest(BaseModel):
    device_id: str
    lang: str = "en"

class TTSRequest(BaseModel):
    text: str
    lang: str = "en"

@app.get("/", response_class=HTMLResponse)
async def read_root():
    try:
        with open("templates/index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    except FileNotFoundError:
        return HTMLResponse(content="<h3>請建立 templates/index.html 檔案。</h3>", status_code=404)


@app.get("/api/settings/api-key")
async def get_api_key_status(device_id: str, db: FirestoreDB = Depends(get_db)):
    user = await db.get_user(device_id)
    user_has = bool(user and user.get("gemini_api_key"))
    env_has = bool(_env_api_key())
    mock_active = await should_use_mock_async(db, device_id)
    configured = user_has or env_has
    if mock_active and not (user_has or env_has):
        source = "mock"
    elif user_has:
        source = "user"
    elif env_has:
        source = "env"
    else:
        source = "none"
    hint = _mask_api_key(user["gemini_api_key"]) if user_has else None
    return {
        "status": "success",
        "configured": configured,
        "source": source,
        "user_saved": user_has,
        "env_available": env_has,
        "hint": hint,
        "mock_mode": mock_active,
        "mock_fallback_enabled": USE_MOCK_API,
        "device_id": device_id,
    }


@app.post("/api/settings/api-key")
async def save_api_key(data: ApiKeySaveRequest, db: FirestoreDB = Depends(get_db)):
    key = (data.api_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="API key is empty")
    check = await verify_gemini_key(key, lang=data.lang)
    if not check["verified"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": check["error"] or "API key verification failed",
                "error_kind": check["error_kind"],
            },
        )
    user = await db.get_user(data.device_id)
    old_key = user.get("gemini_api_key") if user else None
    if old_key and old_key != key:
        _invalidate_genai_cache(old_key)
    await db.save_user(data.device_id, {"gemini_api_key": key})
    _invalidate_genai_cache(key)
    return {
        "status": "success",
        "hint": _mask_api_key(key),
        "user_saved": True,
        "verified": True,
        "verify_error": None,
        "verify_error_kind": None,
        "verified_model": check["model"],
    }


@app.post("/api/settings/api-key/test")
async def test_api_key(data: ApiKeyTestRequest, db: FirestoreDB = Depends(get_db)):
    key = (data.api_key or "").strip() or (await _resolve_api_key_async(db, data.device_id) or "")
    if not key:
        raise HTTPException(status_code=400, detail="No API key to test")
    check = await verify_gemini_key(key, lang=data.lang)
    if not check["verified"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": check["error"] or "API key test failed",
                "error_kind": check["error_kind"],
            },
        )
    return {
        "status": "success",
        "verified": True,
        "hint": _mask_api_key(key),
        "verified_model": check["model"],
    }


@app.delete("/api/settings/api-key")
async def clear_api_key(device_id: str, db: FirestoreDB = Depends(get_db)):
    user = await db.get_user(device_id)
    if user and user.get("gemini_api_key"):
        _invalidate_genai_cache(user["gemini_api_key"].strip())
        await db.delete_user_field(device_id, "gemini_api_key")
    env_has = bool(_env_api_key())
    mock_active = await should_use_mock_async(db, device_id)
    return {
        "status": "success",
        "configured": env_has or mock_active,
        "user_saved": False,
        "env_available": env_has,
        "source": "env" if env_has else ("mock" if mock_active else "none"),
    }


@app.get("/api/settings/maps-key")
async def get_maps_key_status(device_id: str, db: FirestoreDB = Depends(get_db)):
    user = await db.get_user(device_id)
    user_has = bool(user and user.get("google_maps_api_key"))
    env_has = bool(_env_maps_key())
    if user_has:
        source = "user"
    elif env_has:
        source = "env"
    else:
        source = "none"
    return {
        "status": "success",
        "configured": user_has or env_has,
        "source": source,
        "user_saved": user_has,
        "env_available": env_has,
        "hint": _mask_api_key(user["google_maps_api_key"]) if user_has else None,
    }


@app.post("/api/settings/maps-key")
async def save_maps_key(data: MapsKeySaveRequest, db: FirestoreDB = Depends(get_db)):
    key = (data.api_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="Maps API key is empty")
    await db.save_user(data.device_id, {"google_maps_api_key": key})
    return {
        "status": "success",
        "hint": _mask_api_key(key),
        "user_saved": True,
    }


@app.post("/api/settings/maps-key/test")
async def test_maps_key(data: MapsKeyTestRequest, db: FirestoreDB = Depends(get_db)):
    key = (data.api_key or "").strip() or (await _resolve_maps_key_async(db, data.device_id) or "")
    if not key:
        raise HTTPException(status_code=400, detail="No Maps API key to test")
    sample = build_maps_embed_url("Tokyo Station", api_key=key)
    if "embed/v1" not in sample:
        raise HTTPException(status_code=400, detail="Invalid Maps API key format")
    return {"status": "success", "hint": _mask_api_key(key)}


@app.delete("/api/settings/maps-key")
async def clear_maps_key(device_id: str, db: FirestoreDB = Depends(get_db)):
    user = await db.get_user(device_id)
    if user and user.get("google_maps_api_key"):
        await db.delete_user_field(device_id, "google_maps_api_key")
    env_has = bool(_env_maps_key())
    return {
        "status": "success",
        "configured": env_has,
        "user_saved": False,
        "env_available": env_has,
        "source": "env" if env_has else "none",
    }


@app.get("/api/settings/services/health")
async def services_health(device_id: str, db: FirestoreDB = Depends(get_db)):
    user = await db.get_user(device_id)
    user_gemini = bool(user and user.get("gemini_api_key"))
    user_maps = bool(user and user.get("google_maps_api_key"))
    gemini_key = await _resolve_api_key_async(db, device_id)
    maps_key = await _resolve_maps_key_async(db, device_id)
    mock_active = await should_use_mock_async(db, device_id)
    gcp_ok = _gcp_credentials_available()
    return {
        "status": "success",
        "gemini": {
            "available": bool(gemini_key) and not mock_active,
            "mock_mode": mock_active,
            "source": "user" if user_gemini else ("env" if _env_api_key() else "none"),
        },
        "maps": {
            "available": bool(maps_key),
            "embed_api": bool(maps_key),
            "basic_embed_fallback": True,
            "source": "user" if user_maps else ("env" if _env_maps_key() else "none"),
        },
        "tts": {
            "available": not _should_use_mock_tts(),
            "mock_mode": _should_use_mock_tts(),
            "requires_gcp_credentials": True,
            "gcp_configured": gcp_ok,
        },
        "stt": {
            "available": not _should_use_mock_stt(),
            "mock_mode": _should_use_mock_stt(),
            "requires_gcp_credentials": True,
            "gcp_configured": gcp_ok,
        },
        "use_mock_api": USE_MOCK_API,
    }


@app.get("/api/maps/embed-url")
async def maps_embed_url(
    query: str,
    device_id: str = "",
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    db: FirestoreDB = Depends(get_db),
):
    maps_key = await _resolve_maps_key_async(db, device_id or None)
    q = (query or "").strip() or "Japan"
    return {
        "status": "success",
        "embed_url": build_maps_embed_url(q, latitude=latitude, longitude=longitude, api_key=maps_key),
        "open_url": build_maps_open_url(q, latitude=latitude, longitude=longitude),
    }


@app.post("/api/user/init")
async def init_user(data: UserInitRequest, db: FirestoreDB = Depends(get_db)):
    user = await db.get_or_create_user(data.device_id)
    _apply_school_info_to_user(user, data.school_info)
    await db.save_user(data.device_id, {k: v for k, v in user.items() if k != "device_id"})
    await db.sync_completed_tasks(data.device_id, data.completed_tasks)
    profile = profile_from_dict(data.school_info)
    lang = data.school_info.get("lang", "en")

    roadmap = _roadmap_with_links(profile, data.completed_tasks, lang, data.school_info)

    ai_overlay = None
    genai_client = await get_genai_client_async(db, data.device_id)
    if genai_client:
        cached_overlay = None
        if user.get("ai_roadmap") and user.get("ai_roadmap_lang") == lang:
            try:
                cached_overlay = json.loads(user["ai_roadmap"])
            except Exception:
                cached_overlay = None

        if cached_overlay:
            ai_overlay = cached_overlay
        else:
            try:
                ai_overlay = await generate_ai_roadmap(
                    school_info=data.school_info,
                    completed_tasks=data.completed_tasks,
                    lang=lang,
                    genai_client=genai_client,
                )
                if ai_overlay:
                    await db.save_user(data.device_id, {
                        "ai_roadmap": json.dumps(ai_overlay),
                        "ai_roadmap_lang": lang,
                    })
            except Exception as exc:
                print(f"[init_user] AI roadmap generation failed: {exc}")
                ai_overlay = None

    if ai_overlay:
        roadmap = merge_ai_overlay_into_roadmap(roadmap, ai_overlay)

    return {"status": "success", "roadmap": roadmap, "ai_generated": bool(ai_overlay)}

@app.post("/api/user/profile")
async def update_user_profile(data: UserProfileRequest, db: FirestoreDB = Depends(get_db)):
    user = await db.get_user(data.device_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _apply_school_info_to_user(user, data.school_info)
    user["ai_roadmap"] = None
    user["ai_roadmap_lang"] = None
    await db.save_user(data.device_id, {k: v for k, v in user.items() if k != "device_id"})
    completed = await db.get_completed_tasks(data.device_id)
    profile = profile_from_dict(_school_info_from_user(user))
    lang = data.school_info.get("lang", "en")
    roadmap = _roadmap_with_links(profile, completed, lang, data.school_info)

    genai_client = await get_genai_client_async(db, data.device_id)
    if genai_client:
        try:
            ai_overlay = await generate_ai_roadmap(
                school_info=data.school_info,
                completed_tasks=completed,
                lang=lang,
                genai_client=genai_client,
            )
            if ai_overlay:
                await db.save_user(data.device_id, {
                    "ai_roadmap": json.dumps(ai_overlay),
                    "ai_roadmap_lang": lang,
                })
                roadmap = merge_ai_overlay_into_roadmap(roadmap, ai_overlay)
        except Exception as exc:
            print(f"[update_user_profile] AI roadmap regeneration failed: {exc}")

    return {"status": "success", "roadmap": roadmap}

@app.post("/api/roadmap")
async def get_roadmap(data: RoadmapRequest, db: FirestoreDB = Depends(get_db)):
    user = await db.get_user(data.device_id)
    if data.school_info:
        school_info = data.school_info
    elif user:
        school_info = _school_info_from_user(user)
    else:
        school_info = {}
    completed = data.completed_tasks
    if completed is None:
        completed = await db.get_completed_tasks(data.device_id) if user else []
    profile = profile_from_dict(school_info)
    branch_choices = data.branch_choices or {}
    roadmap = _roadmap_with_links(profile, completed, data.lang, school_info, branch_choices)

    if user and user.get("ai_roadmap"):
        try:
            ai_overlay = json.loads(user["ai_roadmap"])
            roadmap = merge_ai_overlay_into_roadmap(roadmap, ai_overlay)
        except Exception:
            pass

    return {"status": "success", "roadmap": roadmap}

@app.post("/api/roadmap/branch")
async def select_roadmap_branch(data: BranchSelectRequest, db: FirestoreDB = Depends(get_db)):
    user = await db.get_user(data.device_id)
    if data.school_info:
        school_info = data.school_info
    elif user:
        school_info = _school_info_from_user(user)
    else:
        school_info = {}
    completed = data.completed_tasks
    if completed is None:
        completed = await db.get_completed_tasks(data.device_id) if user else []
    branch_choices = dict(data.branch_choices or {})
    branch_choices[data.branch_id] = data.choice_id
    profile = profile_from_dict(school_info)
    roadmap = _roadmap_with_links(profile, completed, data.lang, school_info, branch_choices)
    return {
        "status": "success",
        "roadmap": roadmap,
        "branch_choices": branch_choices,
        "completed_tasks": completed,
    }

@app.post("/api/roadmap/task/expand")
async def expand_roadmap_task(data: TaskExpandRequest):
    expansion = get_static_task_expansion(
        data.task_id, data.school_info, data.branch_choices, data.lang
    )
    return {"status": "success", "expansion": expansion}

@app.post("/api/roadmap/task/personalize")
async def personalize_roadmap_task(data: TaskPersonalizeRequest, db: FirestoreDB = Depends(get_db)):
    if await should_use_mock_async(db, data.device_id):
        text = build_mock_personalized_plan(
            data.task_id, data.school_info, data.branch_choices, data.lang
        )
        return {"status": "success", "personalized": {"task_id": data.task_id, "content": text, "mock": True}}

    genai_client = await require_genai_client_async(db, data.device_id)
    target_lang = LANG_MAP.get(data.lang, "English")
    prompt = build_personalize_prompt(
        data.task_id,
        data.school_info,
        data.completed_tasks,
        data.branch_choices,
        data.lang,
        data.current_address,
    )
    try:
        response, _model, _used = await generate_with_model_fallback(
            genai_client,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(
                system_instruction=f"{SYSTEM_INSTRUCTION_BASE}\nReply in {target_lang} only.",
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        text = parse_llm_text_or_json(response.text or "")
        return {"status": "success", "personalized": {"task_id": data.task_id, "content": text, "mock": False}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Personalization failed: {str(e)}")

@app.get("/api/roadmap/schema")
async def roadmap_schema(
    housing_type: str = "dorm",
    part_time_plan: str = "no",
    school_type: str = "language_school",
    lang: str = "en",
    sim_at_airport: bool = False,
    already_exchanged: bool = False,
):
    profile = profile_from_dict({
        "housing_type": housing_type,
        "part_time_plan": part_time_plan,
        "school_type": school_type,
        "sim_at_airport": sim_at_airport,
        "already_exchanged": already_exchanged,
    })
    tasks = get_all_task_ids_for_onboarding(profile, lang)
    roadmap = load_roadmap()
    phases = {p["id"]: pick_i18n(p["title"], lang) for p in roadmap["phases"]}
    for t in tasks:
        t["phase_title"] = phases.get(t["phase"], "")
        t["title"] = pick_i18n(_task_title_by_id(t["id"], roadmap), lang)
    return {"status": "success", "tasks": tasks, "phases": phases}

def _task_title_by_id(task_id: str, roadmap: Dict[str, Any]) -> Dict[str, str]:
    for t in roadmap["tasks"]:
        if t["id"] == task_id:
            return t["title"]
    return {"zh-TW": task_id, "en": task_id, "ja": task_id}

@app.post("/api/tasks/complete")
async def complete_task(data: TaskCompleteRequest, db: FirestoreDB = Depends(get_db)):
    user = await db.get_user(data.device_id)
    completed = await db.get_completed_tasks(data.device_id)
    to_complete = [data.task_id]
    aliases = load_branches().get("completion_aliases") or {}
    for parent, children in aliases.items():
        if data.task_id in children and parent not in to_complete:
            to_complete.append(parent)
    for tid in to_complete:
        if tid not in completed:
            await db.add_completed_task(data.device_id, tid)
            completed.append(tid)
    school_info = _school_info_from_user(user) if user else {}
    profile = profile_from_dict(school_info)
    branch_choices = data.branch_choices or {}
    roadmap = _roadmap_with_links(profile, completed, data.lang, school_info, branch_choices)
    return {"status": "success", "roadmap": roadmap, "completed_tasks": completed}

@app.post("/api/user/sync_tasks")
async def sync_tasks(data: TaskSyncRequest, db: FirestoreDB = Depends(get_db)):
    await db.sync_completed_tasks(data.device_id, data.completed_tasks)
    return {"status": "success"}

@app.post("/api/user/location")
async def update_location(data: LocationUpdateRequest, db: FirestoreDB = Depends(get_db)):
    await db.save_location(data.device_id, data.latitude, data.longitude, data.address)
    return {"status": "success"}

@app.post("/api/agent/latest")
async def get_latest_decision(data: AgentLatestRequest, db: FirestoreDB = Depends(get_db)):
    decision_json = await db.get_agent_decision(data.device_id)
    if decision_json:
        return {"status": "success", "decision": json.loads(decision_json)}
    return {"status": "not_found"}

async def generate_agent_decision(school_info, completed_tasks, current_address, latitude, longitude, local_time, day_of_week, lang, problem_report=None, task_action=None, force_llm=False, device_id=None, db=None):
    # Always try AI first; fall back to rule-based when no key is available
    profile = profile_from_dict(school_info)
    roadmap_data = _roadmap_with_links(profile, completed_tasks, lang, school_info)

    genai_client = await get_genai_client_async(db, device_id)
    use_mock = await should_use_mock_async(db, device_id)

    if use_mock or genai_client is None:
        # No real API key available — return rule-based decision or mock
        if use_mock:
            return get_mock_response(lang, "agent_decision", {
                "expression": "thinking",
                "current_focus_title": bi18n("mockAgentTitle", lang),
                "narrative": bi18n("mockAgentNarrative", lang),
                "action_type": "none",
                "action_label": bi18n("mockAgentActionLabel", lang),
                "action_data": "mock_data",
                "upcoming_hint": bi18n("mockAgentUpcomingHint", lang),
                "newly_completed_tasks": [],
                "source": "mock",
            })
        return build_rule_based_decision(
            roadmap_data, school_info, lang, current_address or "", problem_report, task_action,
        )

    next_tasks = roadmap_data.get("next_tasks", [])
    next_summary = "\n".join([f"- {t['id']}: {t['title']}" for t in next_tasks]) or "All critical tasks completed."

    target_lang = LANG_MAP.get(lang, "English")

    action_context = ""
    if task_action == "completed":
        action_context = """
    [User Action]
    The user reported completing a task. Use the roadmap next tasks below to guide them.
    Do NOT guess task IDs for newly_completed_tasks unless clearly stated; prefer empty array.
        """
    elif problem_report:
        action_context = f"""
    [User Reported Problem]
    The user explicitly reported a problem they are facing right now: '{problem_report}'
    You MUST address this problem in your narrative and provide a solution or guidance for it.
        """

    focus_id = next_tasks[0]["id"] if next_tasks else None
    kb_context = build_kb_context_for_llm(focus_id, lang) if focus_id else ""

    prompt = f"""
    The student is using our relocation roadmap app in Japan. Help with the CURRENT priority task.
    {action_context}

    [Trusted Knowledge Base — use ONLY these facts and URLs; do not invent sources]
    {kb_context}

    [Student Profile]
    - School: {school_info.get('school_name')}
    - Arrival Date: {school_info.get('arrival_date')}
    - Intended Area: {school_info.get('location')}
    - Housing Route: {profile.get('housing_type')}
    - Japanese Level: {school_info.get('japanese_level')}
    - Residence Card at Airport: {school_info.get('has_residence_card', True)}

    [Roadmap Status]
    - Progress: {roadmap_data['progress']['completed']}/{roadmap_data['progress']['total']}
    - Route: {roadmap_data['route']['label']}
    - Recommended next tasks (from roadmap engine, prioritize first):
    {next_summary}
    - Completed Task IDs: {completed_tasks}

    [Real-time Context]
    - Current Location: {current_address} (Coords: {latitude}, {longitude})
    - Local Time: {local_time}, Day: {day_of_week}

    Use Google Search for business hours and nearest facilities when relevant.
    Output JSON with: expression, current_focus_title, narrative, action_type, action_label, action_data, upcoming_hint, newly_completed_tasks (usually empty).
    Respond ONLY in valid JSON. Narrative in {target_lang}.
    """

    try:
        response, _model, _used = await generate_with_model_fallback(
            genai_client,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=f"{SYSTEM_INSTRUCTION_BASE}\nRespond in {target_lang}.",
                tools=[types.Tool(google_search=types.GoogleSearch())]
            ),
        )

        try:
            text = response.text.strip()
        except Exception:
            text = ""

        start_idx = text.find('{')
        end_idx = text.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_str = text[start_idx:end_idx+1]
        else:
            json_str = text

        if not json_str:
            raise ValueError("Response text is empty")
        decision = json.loads(json_str)
        decision["source"] = "llm"
        return decision

    except Exception as exc:
        print(f"[generate_agent_decision] AI failed, falling back to rule-based: {exc}")
        return build_rule_based_decision(
            roadmap_data, school_info, lang, current_address or "", problem_report, task_action,
        )

async def background_decision_task():
    print("Running background agent decision task for all users...")
    db = FirestoreDB()
    try:
        users = await db.get_all_users()
        now = datetime.now(ZoneInfo("Asia/Tokyo"))
        local_time_str = now.strftime("%Y-%m-%dT%H:%M")
        day_str = now.strftime("%A")

        for user in users:
            device_id = user["device_id"]
            last_loc = await db.get_latest_location(device_id)
            if not last_loc:
                continue

            completed = await db.get_completed_tasks(device_id)
            school_info = {
                "school_name": user.get("school_name"),
                "arrival_date": user.get("arrival_date"),
                "location": user.get("location"),
                "japanese_level": user.get("japanese_level"),
                "has_residence_card": user.get("has_residence_card", True),
            }

            try:
                decision = await generate_agent_decision(
                    school_info=school_info,
                    completed_tasks=completed,
                    current_address=last_loc["address"],
                    latitude=last_loc["latitude"],
                    longitude=last_loc["longitude"],
                    local_time=local_time_str,
                    day_of_week=day_str,
                    lang="en",
                    device_id=device_id,
                    db=db,
                )
                await db.save_agent_decision(device_id, json.dumps(decision))
                print(f"Updated decision for {device_id}")
            except Exception as e:
                print(f"Error generating decision for {device_id}: {e}")

    except Exception as e:
        print(f"Background scheduler error: {e}")

@app.post("/api/agent-step")
async def agent_step(data: AgentStepRequest, db: FirestoreDB = Depends(get_db)):
    """
    自律型決策端點：結合即時搜尋，尋找學生居住地或定位點附近的真實政府機構、門市與其營業時間。
    """
    try:
        decision = await generate_agent_decision(
            school_info=data.school_info,
            completed_tasks=data.completed_tasks,
            current_address=data.current_address,
            latitude=data.latitude,
            longitude=data.longitude,
            local_time=data.local_time,
            day_of_week=data.day_of_week,
            lang=data.lang,
            problem_report=data.problem_report,
            task_action=data.task_action,
            force_llm=data.force_llm,
            device_id=data.device_id,
            db=db,
        )

        if data.device_id:
            if "newly_completed_tasks" in decision:
                for t in decision["newly_completed_tasks"]:
                    if t not in data.completed_tasks:
                        await db.add_completed_task(data.device_id, t)
                        data.completed_tasks.append(t)
            await db.save_agent_decision(data.device_id, json.dumps(decision))

        return {"status": "success", "decision": decision, "completed_tasks": data.completed_tasks}
    except Exception as e:
        print(f"Error during agent step: {e}")
        raise HTTPException(status_code=500, detail=f"Agent 決策生成失敗: {str(e)}")

@app.post("/api/export/roadmap-pdf")
async def export_roadmap_pdf(data: RoadmapExportRequest, db: FirestoreDB = Depends(get_db)):
    """Export AI-personalized Haru action plan PDF."""
    profile = profile_from_dict(data.school_info)
    roadmap = _roadmap_with_links(profile, data.completed_tasks, data.lang, data.school_info)
    address = data.current_address or data.school_info.get("location") or ""
    plan = build_action_plan_content(roadmap, data.school_info, data.lang, address)
    if not await should_use_mock_async(db, data.device_id):
        try:
            genai_client = await require_genai_client_async(db, data.device_id)
            plan = await enrich_action_plan_with_ai(
                plan, roadmap, data.school_info, data.lang, address, genai_client
            )
        except Exception as e:
            print(f"Action plan AI enrichment failed, using template: {e}")
            plan["ai_generated"] = False
    try:
        pdf_bytes = build_action_plan_pdf(plan)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"行動計畫產生失敗: {str(e)}")
    filename = f"haru-action-plan-{data.lang}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

# 多輪自由提問 (結構化 blocks + 公式リンク DB)
class ChatMessage(BaseModel):
    role: str
    text: Optional[str] = None
    blocks: Optional[List[Dict[str, Any]]] = None

class ChatRequest(BaseModel):
    message: str
    school_info: Dict[str, Any]
    chat_history: List[ChatMessage]
    lang: str = "en"
    completed_tasks: List[str] = []
    branch_choices: Dict[str, str] = {}
    focus_task_id: Optional[str] = None
    images: Optional[List[Dict[str, str]]] = None  # [{data_base64, mime_type}] max 4
    device_id: Optional[str] = None
    current_address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class QuizStartRequest(BaseModel):
    school_info: Dict[str, Any]
    completed_tasks: List[str] = []
    lang: str = "en"
    focus_task_id: Optional[str] = None

class QuizAnswerRequest(BaseModel):
    quiz_state: Dict[str, Any]
    choice_id: str
    school_info: Dict[str, Any]
    completed_tasks: List[str] = []
    lang: str = "en"
    device_id: Optional[str] = None

CHAT_REPLY_INSTRUCTION = (
    "Reply with plain helpful text only. Do NOT include URLs, markdown links, or website addresses — "
    "official reference links are added automatically by the system. "
    "You have Google Search: use it for current business hours, holidays, and nearest facilities "
    "when the student asks about timing or where to go. "
    "When the student asks WHERE something is or wants directions, you MUST call search_maps_place "
    "so an interactive map appears in chat. "
    "When they ask about procedure flow, what comes next, or their overall roadmap, call "
    "show_roadmap_diagram (scope next_steps, current_phase, or full). "
    "When a custom process diagram or decision tree helps, call render_mermaid with valid Mermaid syntax. "
    "When you lack critical information, call ask_user_question with 2-4 clear choices."
)

@app.get("/api/schools")
async def list_schools(q: str = "", lang: str = "en", limit: int = 25):
    schools = search_schools(q, lang, min(limit, 50))
    return {"status": "success", "schools": schools}

@app.get("/api/knowledge/for-task")
async def knowledge_for_task(task_id: str, lang: str = "en"):
    return {"status": "success", "bundle": get_knowledge_bundle_for_task(task_id, lang)}


@app.get("/api/guides/{guide_id}")
async def get_guide_endpoint(guide_id: str, lang: str = "en"):
    guide = get_guide(guide_id, lang)
    if not guide:
        raise HTTPException(status_code=404, detail="Guide not found")
    return {"status": "success", "guide": guide}


@app.get("/api/resources")
async def get_resources(task_id: str, lang: str = "en", location: str = ""):
    ctx = profile_from_dict({})
    ctx["location"] = location
    items = resolve_resources_for_task(task_id, ctx, lang)
    return {"status": "success", "items": items}

@app.get("/api/chat/suggestions")
async def chat_suggestions(task_id: str, lang: str = "en"):
    chips = build_context_suggested_chips(task_id, lang)
    return {"status": "success", "chips": chips}

@app.post("/api/quiz/start")
async def quiz_start(data: QuizStartRequest):
    result = start_quiz_session(
        data.school_info,
        data.completed_tasks,
        data.lang,
        data.focus_task_id,
    )
    return {"status": "success", **result}


@app.post("/api/quiz/answer")
async def quiz_answer(data: QuizAnswerRequest, db: FirestoreDB = Depends(get_db)):
    result = submit_quiz_answer(
        data.quiz_state,
        data.choice_id,
        data.school_info,
        data.completed_tasks,
        data.lang,
    )
    if result.get("done"):
        genai_client = None
        if not await should_use_mock_async(db, data.device_id):
            genai_client = await get_genai_client_async(db, data.device_id)
        target_lang = LANG_MAP.get(data.lang, "English")
        diagnosis = await synthesize_quiz_diagnosis(
            result["quiz_state"],
            data.school_info,
            data.completed_tasks,
            data.lang,
            genai_client=genai_client,
            target_lang_name=target_lang,
        )
        result["message_blocks"] = diagnosis["message_blocks"]
        result["ai_generated"] = diagnosis.get("ai_generated", False)
        result["source"] = diagnosis.get("source", "rule_engine")
        result["suggested_task_ids"] = diagnosis.get("suggested_task_ids", result.get("suggested_task_ids", []))
    return {"status": "success", **result}


MAX_CHAT_IMAGES = 4


def _normalize_chat_images(images: Optional[List[Dict[str, str]]]) -> List[Dict[str, str]]:
    if not images:
        return []
    return images[:MAX_CHAT_IMAGES]


def _decode_image_b64(data_b64: str) -> bytes:
    import base64
    raw = data_b64.strip()
    if "," in raw and raw.startswith("data:"):
        raw = raw.split(",", 1)[1]
    return base64.b64decode(raw)


def _build_chat_user_parts(message: str, images: List[Dict[str, str]]) -> List[Any]:
    parts: List[Any] = []
    for img in images:
        b64 = img.get("data_base64") or ""
        if not b64:
            continue
        mime = img.get("mime_type") or "image/jpeg"
        try:
            parts.append(types.Part.from_bytes(data=_decode_image_b64(b64), mime_type=mime))
        except Exception:
            continue
    text = message.strip() or (
        f"({len(images)} image(s) attached — please help explain or answer questions about them.)"
        if images else ""
    )
    if text:
        parts.append(types.Part.from_text(text=text))
    return parts


@app.post("/api/chat")
async def chat(data: ChatRequest, db: FirestoreDB = Depends(get_db)):
    focus_task_id = data.focus_task_id
    profile = profile_from_dict(data.school_info)
    effective_completed = merge_effective_completed(profile, data.completed_tasks)
    if not focus_task_id:
        nt = get_next_tasks(profile, effective_completed, limit=1, lang=data.lang)
        focus_task_id = nt[0]["id"] if nt else None

    images = _normalize_chat_images(data.images)
    image_note = ""
    if images:
        image_note = f" User attached {len(images)} image(s)."

    if await should_use_mock_async(db, data.device_id):
        mock_text = get_mock_response(
            data.lang, "chat",
            bi18n("mockChatReply", data.lang, image_note=image_note or "")
        )
        maps_key = await _resolve_maps_key_async(db, data.device_id)
        tool_ctx = {
            "lang": data.lang,
            "school_info": data.school_info,
            "current_address": data.current_address,
            "latitude": data.latitude,
            "longitude": data.longitude,
            "focus_task_id": focus_task_id,
            "completed_tasks": effective_completed,
            "branch_choices": data.branch_choices or {},
            "maps_api_key": maps_key,
        }
        extra_blocks = mock_tool_blocks(data.message, tool_ctx)
        message = merge_chat_blocks(
            mock_text, data.school_info, effective_completed, data.lang, focus_task_id,
            current_address=data.current_address,
            extra_blocks=extra_blocks,
        )
        return {
            "status": "success",
            "message": message,
            "reply": mock_text,
            "suggested_chips": message.get("suggested_chips", []),
            "mock_mode": True,
            "used_search": False,
            "used_tools": bool(extra_blocks),
        }

    target_lang = LANG_MAP.get(data.lang, "English")
    contents = []

    context_intro = (
        f"Context of the user: School: {data.school_info.get('school_name', 'N/A')}, "
        f"Location: {data.school_info.get('location', 'N/A')}, "
        f"Current GPS address: {data.current_address or 'N/A'}, "
        f"Coords: {data.latitude}, {data.longitude}. "
        f"Arrival: {data.school_info.get('arrival_date', 'N/A')}, "
        f"Japanese level: {data.school_info.get('japanese_level', 'N/A')}. "
        f"Completed tasks: {', '.join(effective_completed) or 'none'}. "
        f"Current focus task: {focus_task_id or 'auto'}. "
        f"Please reply strictly in {target_lang}. {CHAT_REPLY_INSTRUCTION}"
    )

    kb_context = build_kb_context_for_llm(focus_task_id, data.lang) if focus_task_id else ""

    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=context_intro)]))
    contents.append(types.Content(role="model", parts=[types.Part.from_text(text="Understood.")]))
    if kb_context:
        contents.append(types.Content(
            role="user",
            parts=[types.Part.from_text(text=kb_context)],
        ))
        contents.append(types.Content(role="model", parts=[types.Part.from_text(text="I will use only the trusted knowledge above.")]))

    for msg in data.chat_history:
        msg_data = msg.model_dump() if hasattr(msg, "model_dump") else msg.dict()
        hist_text = message_to_history_text(msg_data)
        if not hist_text:
            continue
        contents.append(types.Content(
            role="user" if msg.role == "user" else "model",
            parts=[types.Part.from_text(text=hist_text)]
        ))

    user_parts = _build_chat_user_parts(data.message, images)
    if not user_parts:
        raise HTTPException(status_code=400, detail="Empty message")
    contents.append(types.Content(role="user", parts=user_parts))

    try:
        genai_client = await require_genai_client_async(db, data.device_id)
        maps_key = await _resolve_maps_key_async(db, data.device_id)
        tool_ctx = {
            "lang": data.lang,
            "school_info": data.school_info,
            "current_address": data.current_address,
            "latitude": data.latitude,
            "longitude": data.longitude,
            "focus_task_id": focus_task_id,
            "completed_tasks": effective_completed,
            "branch_choices": data.branch_choices or {},
            "maps_api_key": maps_key,
        }
        system_instruction = (
            f"{SYSTEM_INSTRUCTION_BASE}\n{CHAT_REPLY_INSTRUCTION}\n"
            f"Your response must be in {target_lang}."
        )
        text, tool_blocks, used_search = await run_chat_with_tools(
            genai_client,
            contents,
            system_instruction=system_instruction,
            lang=data.lang,
            context=tool_ctx,
            generate_fn=generate_with_model_fallback,
        )
        if not tool_blocks:
            tool_blocks = mock_tool_blocks(data.message, tool_ctx)
        message = merge_chat_blocks(
            text, data.school_info, effective_completed, data.lang, focus_task_id,
            current_address=data.current_address,
            extra_blocks=tool_blocks,
        )
        return {
            "status": "success",
            "message": message,
            "reply": text,
            "suggested_chips": message.get("suggested_chips", []),
            "used_search": used_search,
            "used_tools": bool(tool_blocks),
            "mock_mode": False,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"對話處理失敗: {str(e)}")

@app.post("/api/analyze-form")
async def analyze_form(
    file: UploadFile = File(...),
    school_name: str = Form(""),
    location: str = Form(""),
    lang: str = Form("en"),
    device_id: str = Form(""),
    db: FirestoreDB = Depends(get_db),
):
    if await should_use_mock_async(db, device_id or None):
        return {"status": "success", "analysis": get_mock_response(lang, "analyze_form", bi18n("mockAnalyzeForm", lang))}
        
    target_lang = LANG_MAP.get(lang, "English")
    try:
        contents_bytes = await file.read()
        image_part = types.Part.from_bytes(
            data=contents_bytes,
            mime_type=file.content_type
        )
        
        prompt = (
            f"Analyze this Japanese paper form/notice for an international student at {school_name}, living in {location}."
            f"Write strictly in {target_lang}."
        )
        
        genai_client = await require_genai_client_async(db, device_id or None)
        response, _model, _used = await generate_with_model_fallback(
            genai_client,
            contents=[image_part, prompt],
            config=types.GenerateContentConfig(
                system_instruction=f"{SYSTEM_INSTRUCTION_BASE}\nEnsure analysis is in {target_lang}."
            ),
        )
        
        return {"status": "success", "analysis": response.text}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"影像分析失敗: {str(e)}")

@app.post("/api/tts")
async def generate_speech(data: TTSRequest):
    if _should_use_mock_tts():
        mock_audio_base64 = "//OQAxAAAAANIAAAAAExBTUUzLjEwMKqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq"
        return {"status": "success", "audio": mock_audio_base64}
        
    try:
        client = texttospeech.TextToSpeechAsyncClient()
        input_text = texttospeech.SynthesisInput(text=data.text)
        
        voice_map = {k: v[1] for k, v in TTS_VOICES.items()}
        lang_map = {k: v[0] for k, v in TTS_VOICES.items()}
        
        voice = texttospeech.VoiceSelectionParams(
            language_code=lang_map.get(data.lang, "cmn-TW"),
            name=voice_map.get(data.lang, "cmn-TW-Wavenet-A")
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )
        
        response = await client.synthesize_speech(
            request={"input": input_text, "voice": voice, "audio_config": audio_config}
        )
        
        audio_base64 = base64.b64encode(response.audio_content).decode("utf-8")
        return {"status": "success", "audio": audio_base64}
    except Exception as e:
        print(f"TTS Error: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/api/stt")
async def speech_to_text(file: UploadFile = File(...), lang: str = Form("en")):
    if _should_use_mock_stt():
        return {"status": "success", "text": get_mock_response(lang, "stt", bi18n("mockSttResult", lang))}
        
    try:
        client = speech.SpeechAsyncClient()
        audio_content = await file.read()
        
        audio = speech.RecognitionAudio(content=audio_content)
        
        lang_map = STT_LANGUAGE_CODES
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
            sample_rate_hertz=STT_SAMPLE_RATE_HZ,
            language_code=lang_map.get(lang, "en-US"),
        )
        
        response = await client.recognize(config=config, audio=audio)
        
        transcript = ""
        for result in response.results:
            transcript += result.alternatives[0].transcript
            
        return {"status": "success", "text": transcript}
    except Exception as e:
        print(f"STT Error: {e}")
        return {"status": "error", "message": str(e)}