"""
Firestore persistence with in-memory fallback when credentials are missing.
"""
from __future__ import annotations

import hashlib
import os
import time
import uuid
from collections import deque
from typing import Any

_firebase_app = None
_db = None
_memory: dict[str, Any] = {
    "threats": deque(maxlen=500),
    "logs": deque(maxlen=1000),
    "analytics_events": deque(maxlen=2000),
    "blocked_prompts": {},
}


def init_firebase() -> bool:
    global _firebase_app, _db
    if _firebase_app is not None:
        return _db is not None
    cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if not cred_path or not os.path.isfile(cred_path):
        return False
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_path)
            _firebase_app = firebase_admin.initialize_app(cred)
        _db = firestore.client()
        return True
    except Exception:
        _db = None
        return False


def _collection(name: str):
    if _db is not None:
        return _db.collection(name)
    return None


def log_event(level: str, event: str, detail: str, meta: dict | None = None) -> dict:
    rec = {
        "id": str(uuid.uuid4()),
        "ts": time.time(),
        "level": level,
        "event": event,
        "detail": detail,
        "meta": meta or {},
    }
    col = _collection("logs")
    if col is not None:
        col.document(rec["id"]).set(rec)
    else:
        _memory["logs"].appendleft(rec)
    return rec


def add_threat(
    user_id: str | None,
    message: str,
    threat_score: float,
    blocked: bool,
    categories: list[str],
) -> dict:
    preview = message[:180] + ("…" if len(message) > 180 else "")
    rec = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "message_preview": preview,
        "full_hash": hashlib.sha256(message.encode("utf-8", errors="ignore")).hexdigest(),
        "threat_score": threat_score,
        "blocked": blocked,
        "categories": categories,
        "timestamp": time.time(),
    }
    col = _collection("threats")
    if col is not None:
        col.document(rec["id"]).set(rec)
    else:
        _memory["threats"].appendleft(rec)

    if blocked:
        bp = _collection("blocked_prompts")
        key = rec["full_hash"]
        if bp is not None:
            doc = bp.document(key)
            snap = doc.get()
            c = (snap.to_dict() or {}).get("count", 0) + 1
            doc.set({"prompt_hash": key, "count": c, "last_reason": categories[:5], "updated": time.time()})
        else:
            d = _memory["blocked_prompts"].get(key, {"count": 0})
            d["count"] = d.get("count", 0) + 1
            d["categories"] = categories
            _memory["blocked_prompts"][key] = d

    bump_analytics(blocked, categories)
    return rec


def bump_analytics(blocked: bool, categories: list[str]) -> None:
    col = _collection("analytics")
    if col is not None:
        doc = col.document("summary")
        snap = doc.get()
        data = snap.to_dict() or {}
        data["total_scans"] = int(data.get("total_scans", 0)) + 1
        if blocked:
            data["blocked_count"] = int(data.get("blocked_count", 0)) + 1
        by_cat = data.get("by_category", {})
        for c in categories:
            by_cat[c] = int(by_cat.get(c, 0)) + 1
        data["by_category"] = by_cat
        data["updated"] = time.time()
        doc.set(data)
    else:
        _memory["analytics_events"].append(
            {"blocked": blocked, "categories": categories, "ts": time.time()}
        )


def list_threats(limit: int = 100) -> list[dict]:
    col = _collection("threats")
    if col is not None:
        try:
            from google.cloud.firestore_v1 import Query

            docs = col.order_by("timestamp", direction=Query.DESCENDING).limit(limit).stream()
            return [{**(d.to_dict() or {}), "id": d.id} for d in docs]
        except Exception:
            rows = [{**(d.to_dict() or {}), "id": d.id} for d in col.stream()]
            rows.sort(key=lambda x: float(x.get("timestamp") or 0), reverse=True)
            return rows[:limit]
    return list(_memory["threats"])[:limit]


def list_logs(limit: int = 200) -> list[dict]:
    col = _collection("logs")
    if col is not None:
        try:
            from google.cloud.firestore_v1 import Query

            docs = col.order_by("ts", direction=Query.DESCENDING).limit(limit).stream()
            return [{**(d.to_dict() or {}), "id": d.id} for d in docs]
        except Exception:
            rows = [{**(d.to_dict() or {}), "id": d.id} for d in col.stream()]
            rows.sort(key=lambda x: float(x.get("ts") or 0), reverse=True)
            return rows[:limit]
    return list(_memory["logs"])[:limit]


def get_analytics_summary() -> dict[str, Any]:
    col = _collection("analytics")
    timeline: list[dict] = []
    if col is not None:
        doc = col.document("summary").get()
        data = doc.to_dict() or {}
        total = int(data.get("total_scans", 0))
        blocked = int(data.get("blocked_count", 0))
        by_cat = data.get("by_category", {})
        # Timeline from threats collection (sample last 24 buckets)
        threats = list_threats(120)
        buckets: dict[str, int] = {}
        for t in threats:
            day = time.strftime("%Y-%m-%d %H:00", time.localtime(t.get("timestamp", 0)))
            buckets[day] = buckets.get(day, 0) + 1
        timeline = [{"t": k, "count": v} for k, v in sorted(buckets.items())][-24:]
        avg = sum(x.get("threat_score", 0) for x in threats) / max(len(threats), 1)
        return {
            "total_scans": total,
            "blocked_count": blocked,
            "avg_threat_score": round(avg, 2),
            "by_category": by_cat,
            "timeline": timeline,
        }

    events = list(_memory["analytics_events"])
    total = len(events)
    blocked = sum(1 for e in events if e.get("blocked"))
    by_cat: dict[str, int] = {}
    for e in events:
        for c in e.get("categories", []):
            by_cat[c] = by_cat.get(c, 0) + 1
    threats = list(_memory["threats"])
    avg = sum(t.get("threat_score", 0) for t in threats) / max(len(threats), 1)
    # simple timeline from threats
    buckets = {}
    for t in threats:
        day = time.strftime("%Y-%m-%d %H:%M", time.localtime(t.get("timestamp", 0)))
        buckets[day] = buckets.get(day, 0) + 1
    timeline = [{"t": k, "count": v} for k, v in sorted(buckets.items())][-24:]
    return {
        "total_scans": total,
        "blocked_count": blocked,
        "avg_threat_score": round(avg, 2),
        "by_category": by_cat,
        "timeline": timeline,
    }


def ensure_demo_user(email: str, password_hash: str, role: str = "admin") -> None:
    col = _collection("users")
    if col is None:
        return
    doc = col.document(email.replace("@", "_at_"))
    if not doc.get().exists:
        doc.set(
            {
                "email": email,
                "password_hash": password_hash,
                "role": role,
                "risk_score": 0.0,
                "created": time.time(),
            }
        )
