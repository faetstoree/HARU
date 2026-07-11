"""
Firestore data access layer — replaces SQLAlchemy / SQLite.

Collections:
  users/{device_id}           — user profile + API keys + AI overlay cache
  users/{device_id}/tasks/{task_id}  — completed tasks
  location_logs/{device_id}   — latest GPS location (overwritten each time)
  agent_decisions/{device_id} — latest agent decision cache

Usage (mirrors the old SQLAlchemy Session interface used in main.py):
  from firestore_db import get_db, FirestoreDB
  db = FirestoreDB()
  user = db.get_user(device_id)
  db.save_user(device_id, {...})
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from google.cloud import firestore

# ---------------------------------------------------------------------------
# Client singleton
# ---------------------------------------------------------------------------

_client: Optional[firestore.AsyncClient] = None


def _get_client() -> firestore.AsyncClient:
    global _client
    if _client is None:
        # On Cloud Run, project is auto-detected from the metadata server.
        # Locally, set GOOGLE_CLOUD_PROJECT in .env.
        project = os.getenv("GOOGLE_CLOUD_PROJECT") or None
        _client = firestore.AsyncClient(project=project)
    return _client


# ---------------------------------------------------------------------------
# Plain-dict model helpers (replaces SQLAlchemy model objects)
# ---------------------------------------------------------------------------

def _default_user() -> Dict[str, Any]:
    return {
        "school_name": None,
        "arrival_date": None,
        "location": None,
        "japanese_level": None,
        "has_residence_card": True,
        "housing_type": "dorm",
        "school_type": "language_school",
        "part_time_plan": "no",
        "sim_at_airport": False,
        "already_exchanged": False,
        "permit_obtained": False,
        "gemini_api_key": None,
        "google_maps_api_key": None,
        "ai_roadmap": None,
        "ai_roadmap_lang": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# FirestoreDB — async data access
# ---------------------------------------------------------------------------

class FirestoreDB:
    """Thin async wrapper around Firestore that matches the access patterns in main.py."""

    def __init__(self):
        # Don't initialize the client here — wait until first actual DB call.
        self._db: Optional[firestore.AsyncClient] = None

    def _client(self) -> firestore.AsyncClient:
        if self._db is None:
            self._db = _get_client()
        return self._db

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    async def get_user(self, device_id: str) -> Optional[Dict[str, Any]]:
        doc = await self._client().collection("users").document(device_id).get()
        if doc.exists:
            data = doc.to_dict()
            data["device_id"] = device_id
            return data
        return None

    async def get_or_create_user(self, device_id: str) -> Dict[str, Any]:
        user = await self.get_user(device_id)
        if user is None:
            user = _default_user()
            user["device_id"] = device_id
            await self._client().collection("users").document(device_id).set(user)
        return user

    async def save_user(self, device_id: str, fields: Dict[str, Any]) -> None:
        await self._client().collection("users").document(device_id).set(
            fields, merge=True
        )

    async def delete_user_field(self, device_id: str, field: str) -> None:
        await self._client().collection("users").document(device_id).update(
            {field: firestore.DELETE_FIELD}
        )

    async def get_completed_tasks(self, device_id: str) -> List[str]:
        docs = (
            await self._client().collection("users")
            .document(device_id)
            .collection("tasks")
            .get()
        )
        return [doc.id for doc in docs]

    async def add_completed_task(self, device_id: str, task_id: str) -> None:
        await (
            self._client().collection("users")
            .document(device_id)
            .collection("tasks")
            .document(task_id)
            .set({"status": "completed", "created_at": firestore.SERVER_TIMESTAMP})
        )

    async def sync_completed_tasks(
        self, device_id: str, task_ids: List[str]
    ) -> None:
        tasks_ref = (
            self._client().collection("users").document(device_id).collection("tasks")
        )
        existing = await tasks_ref.get()
        for doc in existing:
            await doc.reference.delete()
        for tid in task_ids:
            await tasks_ref.document(tid).set(
                {"status": "completed", "created_at": firestore.SERVER_TIMESTAMP}
            )

    async def save_location(
        self,
        device_id: str,
        latitude: float,
        longitude: float,
        address: str,
    ) -> None:
        await self._client().collection("location_logs").document(device_id).set(
            {
                "device_id": device_id,
                "latitude": latitude,
                "longitude": longitude,
                "address": address,
                "timestamp": firestore.SERVER_TIMESTAMP,
            }
        )

    async def get_latest_location(self, device_id: str) -> Optional[Dict[str, Any]]:
        doc = await self._client().collection("location_logs").document(device_id).get()
        if doc.exists:
            return doc.to_dict()
        return None

    async def save_agent_decision(self, device_id: str, decision_json: str) -> None:
        await self._client().collection("agent_decisions").document(device_id).set(
            {
                "device_id": device_id,
                "decision_data": decision_json,
                "updated_at": firestore.SERVER_TIMESTAMP,
            }
        )

    async def get_agent_decision(self, device_id: str) -> Optional[str]:
        doc = (
            await self._client().collection("agent_decisions").document(device_id).get()
        )
        if doc.exists:
            return doc.to_dict().get("decision_data")
        return None

    async def get_all_users(self) -> List[Dict[str, Any]]:
        docs = await self._client().collection("users").get()
        result = []
        for doc in docs:
            data = doc.to_dict()
            data["device_id"] = doc.id
            result.append(data)
        return result


# ---------------------------------------------------------------------------
# FastAPI dependency — yields a FirestoreDB instance
# ---------------------------------------------------------------------------

async def get_db() -> FirestoreDB:  # type: ignore[return]
    """FastAPI dependency. Use with `db: FirestoreDB = Depends(get_db)`."""
    return FirestoreDB()
