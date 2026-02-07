from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from .resilience import retry_with_backoff
from .settings import get_settings

SETTINGS = get_settings()


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


def _append_event(
    state: dict[str, Any],
    session_id: str,
    agent_name: str,
    event_type: str,
    summary: str,
    artifact_refs: list[str] | None = None,
) -> None:
    state.setdefault("events", []).append(
        {
            "timestamp": _now_iso(),
            "session_id": session_id,
            "agent_name": agent_name,
            "event_type": event_type,
            "summary": summary,
            "artifact_refs": artifact_refs or [],
        }
    )


def _priority_from_minutes(minutes: int) -> str:
    if minutes >= 120:
        return "high"
    if minutes >= 70:
        return "medium"
    return "low"


def _heuristic_estimate(topic: str, evidence_summary: str, source_count: int) -> dict[str, Any]:
    words = max(1, len(re.findall(r"[A-Za-z0-9]+", topic)))
    evidence_words = len(re.findall(r"[A-Za-z0-9]+", evidence_summary))
    base = 30 + (words * 8)
    evidence_factor = min(40, evidence_words * 2)
    source_factor = min(35, source_count * 7)
    minutes = int(max(25, min(240, base + evidence_factor + source_factor)))
    priority = _priority_from_minutes(minutes)
    confidence = round(min(0.95, 0.45 + (source_count * 0.12) + (0.01 * min(20, evidence_words))), 2)
    return {
        "estimated_minutes": minutes,
        "priority": priority,
        "confidence": confidence,
        "rationale": "Heuristic estimate from topic complexity and source coverage.",
    }


def _gemini_estimate(topic: str, evidence_summary: str, source_count: int) -> dict[str, Any]:
    if not SETTINGS.google_api_key:
        return _heuristic_estimate(topic, evidence_summary, source_count)

    client = genai.Client(api_key=SETTINGS.google_api_key)
    prompt = (
        "Estimate study effort for one midterm topic. Return strict JSON object only with keys: "
        "estimated_minutes (int), priority (high|medium|low), confidence (0-1 float), rationale.\n"
        f"Topic: {topic}\n"
        f"Evidence: {evidence_summary}\n"
        f"Source count: {source_count}\n"
        "Constraints: estimated_minutes between 25 and 240. Keep rationale under 20 words."
    )
    def _call() -> dict[str, Any]:
        resp = client.models.generate_content(
            model=SETTINGS.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )
        raw = (resp.text or "").strip()
        parsed = json.loads(raw)
        minutes = int(parsed.get("estimated_minutes", 60))
        minutes = int(max(25, min(240, minutes)))
        priority = str(parsed.get("priority", _priority_from_minutes(minutes))).lower().strip()
        if priority not in {"high", "medium", "low"}:
            priority = _priority_from_minutes(minutes)
        confidence = float(parsed.get("confidence", 0.65))
        confidence = round(max(0.0, min(1.0, confidence)), 2)
        rationale = str(parsed.get("rationale", "Model estimate")).strip()[:180]
        return {
            "estimated_minutes": minutes,
            "priority": priority,
            "confidence": confidence,
            "rationale": rationale or "Model estimate",
        }

    try:
        return retry_with_backoff(
            _call,
            max_retries=SETTINGS.max_gemini_retries,
            base_seconds=SETTINGS.retry_base_seconds,
        )
    except Exception:
        return _heuristic_estimate(topic, evidence_summary, source_count)


def estimate_workload(
    session_id: str,
    min_minutes: int = 25,
    max_minutes: int = 240,
    force_reprocess: bool = False,
) -> dict[str, Any]:
    state = _load_state(session_id)
    ingestion_rows = state.get("ingestion_state", {}).get("course_topic_evidence", [])
    if not ingestion_rows:
        raise ValueError("No course_topic_evidence found. Run ingestion first.")

    existing = state.get("estimation_state", {}).get("topic_estimates", [])
    if existing and not force_reprocess:
        return {
            "session_id": session_id,
            "status": "complete",
            "topic_estimates_count": len(existing),
            "uncertainty_flags": state.get("estimation_state", {}).get("uncertainty_flags", []),
            "reused_existing": True,
        }

    topic_estimates: list[dict[str, Any]] = []
    uncertainty_flags: list[str] = []
    for row in ingestion_rows:
        topic = str(row.get("topic", "")).strip()
        course_id = str(row.get("course_id", "")).strip()
        evidence_summary = str(row.get("evidence_summary", "")).strip()
        source_files = row.get("source_files", [])
        if not topic or not course_id:
            continue
        estimate = _gemini_estimate(topic, evidence_summary, len(source_files))
        minutes = int(max(min_minutes, min(max_minutes, estimate["estimated_minutes"])))
        confidence = float(estimate["confidence"])
        if confidence < 0.6:
            uncertainty_flags.append(f"Low confidence estimate for {course_id}:{topic}")

        topic_estimates.append(
            {
                "course_id": course_id,
                "topic": topic,
                "estimated_minutes": minutes,
                "priority": estimate["priority"],
                "confidence": round(confidence, 2),
                "rationale": estimate["rationale"],
                "source_files": source_files,
            }
        )

    state["status"] = "planning"
    state["estimation_state"] = {
        "topic_estimates": topic_estimates,
        "uncertainty_flags": sorted(set(uncertainty_flags)),
    }
    _append_event(
        state,
        session_id=session_id,
        agent_name="EstimationAgent",
        event_type="complete",
        summary=f"Generated {len(topic_estimates)} workload estimates.",
        artifact_refs=[f"estimates:{len(topic_estimates)}"],
    )
    _save_state(session_id, state)
    return {
        "session_id": session_id,
        "status": "complete",
        "topic_estimates_count": len(topic_estimates),
        "uncertainty_flags": state["estimation_state"]["uncertainty_flags"],
        "reused_existing": False,
    }


def get_session_estimation_state(session_id: str) -> dict[str, Any]:
    state = _load_state(session_id)
    return {
        "session_id": state.get("session_id", session_id),
        "status": state.get("status", ""),
        "estimation_state": state.get("estimation_state", {}),
        "events": state.get("events", []),
    }
