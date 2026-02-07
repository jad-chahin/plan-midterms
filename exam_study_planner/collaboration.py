from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .settings import get_settings

SETTINGS = get_settings()

ALLOWED_EVENT_TYPES = {"invoke", "handoff", "review", "revision", "complete", "error"}


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _session_dir(session_id: str) -> Path:
    return SETTINGS.artifacts_dir / "sessions" / session_id


def _state_path(session_id: str) -> Path:
    return _session_dir(session_id) / "state.json"


def _load_state(session_id: str) -> dict[str, Any]:
    path = _state_path(session_id)
    if not path.exists():
        raise ValueError(f"Session state not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _save_state(session_id: str, state: dict[str, Any]) -> None:
    session_dir = _session_dir(session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _now_iso()
    _state_path(session_id).write_text(
        json.dumps(state, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )


def record_collaboration_event(
    session_id: str,
    agent_name: str,
    event_type: str,
    summary: str,
    artifact_refs: list[str] | None = None,
) -> dict[str, Any]:
    state = _load_state(session_id)
    normalized_type = event_type.strip().lower()
    if normalized_type not in ALLOWED_EVENT_TYPES:
        raise ValueError(
            f"Invalid event_type '{event_type}'. Allowed: {sorted(ALLOWED_EVENT_TYPES)}."
        )
    event = {
        "timestamp": _now_iso(),
        "session_id": session_id,
        "agent_name": agent_name.strip() or "UnknownAgent",
        "event_type": normalized_type,
        "summary": summary.strip(),
        "artifact_refs": sorted(set(artifact_refs or [])),
    }
    state.setdefault("events", []).append(event)
    _save_state(session_id, state)
    return {"session_id": session_id, "event": event}


def read_collaboration_trace(
    session_id: str,
    limit: int = 100,
    event_types: list[str] | None = None,
) -> dict[str, Any]:
    state = _load_state(session_id)
    events = list(state.get("events", []))
    normalized_filter = {
        item.strip().lower()
        for item in (event_types or [])
        if item and item.strip().lower() in ALLOWED_EVENT_TYPES
    }
    if normalized_filter:
        events = [e for e in events if str(e.get("event_type", "")).lower() in normalized_filter]
    if limit > 0:
        events = events[-limit:]
    return {
        "session_id": session_id,
        "total_events": len(state.get("events", [])),
        "returned_events": len(events),
        "events": events,
    }
