"""One-shot migration: replace Chinese japanese_level values with language-neutral codes.

Old values (stored when UI used Chinese option values):
  零基礎 → beginner_zero
  初級   → beginner
  中級   → intermediate
  高級   → advanced

Run once:
    python scripts/migrate_japanese_level.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from database import SessionLocal  # noqa: E402
from models import User             # noqa: E402

LEGACY_MAP = {
    "零基礎": "beginner_zero",
    "初級":   "beginner",
    "中級":   "intermediate",
    "高級":   "advanced",
}


def main() -> None:
    db = SessionLocal()
    try:
        users = db.query(User).all()
        updated = 0
        for user in users:
            new_val = LEGACY_MAP.get(user.japanese_level)
            if new_val:
                print(f"  device={user.device_id[:12]}…  {user.japanese_level!r} → {new_val!r}")
                user.japanese_level = new_val
                updated += 1
        db.commit()
        print(f"\nDone. {updated}/{len(users)} rows updated.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
