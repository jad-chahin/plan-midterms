from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from .settings import get_settings

SETTINGS = get_settings()


@dataclass
class TopicTask:
    course_id: str
    course_name: str
    course_midterm: date
    topic: str
    remaining_minutes: int
    priority: str
    source_files: list[str]


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


def _priority_rank(priority: str) -> int:
    p = priority.lower().strip()
    if p == "high":
        return 0
    if p == "medium":
        return 1
    return 2


def _date_range(start: date, end: date) -> list[date]:
    days: list[date] = []
    cur = start
    while cur <= end:
        days.append(cur)
        cur = cur + timedelta(days=1)
    return days


def _build_tasks(state: dict[str, Any]) -> tuple[list[TopicTask], date]:
    courses = state.get("user_inputs", {}).get("courses", [])
    course_map: dict[str, dict[str, Any]] = {c["course_id"]: c for c in courses if c.get("course_id")}
    if not course_map:
        raise ValueError("No courses found in user_inputs. Register courses first.")

    estimates = state.get("estimation_state", {}).get("topic_estimates", [])
    if not estimates:
        raise ValueError("No topic_estimates found. Run estimation first.")

    tasks: list[TopicTask] = []
    last_midterm = max(date.fromisoformat(c["midterm_date"]) for c in courses)
    for est in estimates:
        course_id = str(est.get("course_id", "")).strip()
        if course_id not in course_map:
            continue
        course = course_map[course_id]
        minutes = int(est.get("estimated_minutes", 0))
        if minutes <= 0:
            continue
        tasks.append(
            TopicTask(
                course_id=course_id,
                course_name=str(course.get("course_name", course_id)),
                course_midterm=date.fromisoformat(course["midterm_date"]),
                topic=str(est.get("topic", "General Review")).strip() or "General Review",
                remaining_minutes=minutes,
                priority=str(est.get("priority", "medium")),
                source_files=[str(x) for x in est.get("source_files", [])],
            )
        )

    if not tasks:
        raise ValueError("No valid estimate tasks available for planning.")
    return tasks, last_midterm


def _pick_next_task(tasks: list[TopicTask], current_date: date) -> TopicTask | None:
    eligible = [t for t in tasks if t.remaining_minutes > 0 and current_date <= t.course_midterm]
    if not eligible:
        return None

    def sort_key(t: TopicTask) -> tuple[int, int, int]:
        days_left = max(0, (t.course_midterm - current_date).days)
        return (days_left, _priority_rank(t.priority), -t.remaining_minutes)

    eligible.sort(key=sort_key)
    return eligible[0]


def build_schedule_plan(
    session_id: str,
    daily_study_cap_minutes: int = 240,
    min_block_minutes: int = 30,
    max_block_minutes: int = 90,
    force_reprocess: bool = False,
) -> dict[str, Any]:
    state = _load_state(session_id)
    existing = state.get("planning_state", {}).get("plan_rows", [])
    if existing and not force_reprocess:
        return {
            "session_id": session_id,
            "status": "complete",
            "reused_existing": True,
            "plan_rows_count": len(existing),
            "date_start": existing[0]["date"] if existing else "",
            "date_end": state.get("planning_state", {}).get("last_midterm_date", ""),
        }

    tasks, last_midterm = _build_tasks(state)
    start_date = date.today()
    if last_midterm < start_date:
        raise ValueError(
            f"Cannot plan: all midterms are in the past (today={start_date.isoformat()}, last_midterm={last_midterm.isoformat()})."
        )

    plan_rows: list[dict[str, Any]] = []
    timeline = _date_range(start_date, last_midterm)
    for day in timeline:
        remaining_day = max(0, int(daily_study_cap_minutes))
        wrote_any = False
        while remaining_day >= min_block_minutes:
            task = _pick_next_task(tasks, current_date=day)
            if not task:
                break
            block = min(max_block_minutes, task.remaining_minutes, remaining_day)
            if block < min_block_minutes and task.remaining_minutes >= min_block_minutes:
                break
            task.remaining_minutes -= block
            remaining_day -= block
            wrote_any = True
            plan_rows.append(
                {
                    "date": day.isoformat(),
                    "course": task.course_name,
                    "topic": task.topic,
                    "task_description": f"Study and practice {task.topic}.",
                    "estimated_minutes": int(block),
                    "priority": task.priority.lower().strip() or "medium",
                    "source_files": task.source_files,
                    "status": "planned",
                }
            )

        if not wrote_any:
            plan_rows.append(
                {
                    "date": day.isoformat(),
                    "course": "General",
                    "topic": "Buffer/Review",
                    "task_description": "Buffer day for review, catch-up, or rest.",
                    "estimated_minutes": 0,
                    "priority": "low",
                    "source_files": [],
                    "status": "planned",
                }
            )

    unscheduled = [t for t in tasks if t.remaining_minutes > 0]
    warnings: list[str] = []
    if unscheduled:
        warnings.append(
            f"{len(unscheduled)} topics could not be fully scheduled before their midterm dates."
        )

    previous_version = int(state.get("planning_state", {}).get("plan_version", 0))
    state["status"] = "reviewing"
    state["planning_state"] = {
        "plan_version": previous_version + 1,
        "last_midterm_date": last_midterm.isoformat(),
        "plan_rows": plan_rows,
        "warnings": warnings,
    }
    _append_event(
        state,
        session_id=session_id,
        agent_name="PlanningReviewerAgent",
        event_type="complete",
        summary=(
            f"Generated {len(plan_rows)} day-by-day plan rows "
            f"from {start_date.isoformat()} to {last_midterm.isoformat()}."
        ),
        artifact_refs=[f"plan_rows:{len(plan_rows)}"],
    )
    _save_state(session_id, state)
    return {
        "session_id": session_id,
        "status": "complete",
        "reused_existing": False,
        "plan_rows_count": len(plan_rows),
        "date_start": start_date.isoformat(),
        "date_end": last_midterm.isoformat(),
        "warnings": warnings,
    }


def get_session_planning_state(session_id: str) -> dict[str, Any]:
    state = _load_state(session_id)
    return {
        "session_id": state.get("session_id", session_id),
        "status": state.get("status", ""),
        "planning_state": state.get("planning_state", {}),
        "events": state.get("events", []),
    }
