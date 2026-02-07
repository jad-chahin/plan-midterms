from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from .planning import build_schedule_plan
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


def _date_range(start: date, end: date) -> list[str]:
    out: list[str] = []
    cur = start
    while cur <= end:
        out.append(cur.isoformat())
        cur = cur + timedelta(days=1)
    return out


def _is_capacity_limited_only(validation_report: dict[str, Any]) -> bool:
    return (
        not bool(validation_report.get("coverage_ok", True))
        and bool(validation_report.get("date_range_ok", False))
        and bool(validation_report.get("load_balance_ok", False))
        and bool(validation_report.get("deadline_ok", False))
        and bool(validation_report.get("capacity_shortfall_detected", False))
    )


def _validate_plan(state: dict[str, Any], daily_cap: int) -> tuple[dict[str, Any], list[str]]:
    planning_state = state.get("planning_state", {})
    plan_rows = planning_state.get("plan_rows", [])
    courses = state.get("user_inputs", {}).get("courses", [])
    estimates = state.get("estimation_state", {}).get("topic_estimates", [])
    if not plan_rows:
        raise ValueError("No plan_rows found. Run planning first.")

    course_midterms = {
        c["course_name"]: date.fromisoformat(c["midterm_date"])
        for c in courses
        if c.get("course_name") and c.get("midterm_date")
    }
    last_midterm = max(date.fromisoformat(c["midterm_date"]) for c in courses)
    today = date.today()

    all_plan_dates = {r["date"] for r in plan_rows if r.get("date")}
    required_dates = set(_date_range(today, last_midterm))
    date_range_ok = required_dates.issubset(all_plan_dates)

    covered_topics = {
        (str(r.get("course", "")).strip(), str(r.get("topic", "")).strip().lower())
        for r in plan_rows
        if str(r.get("course", "")).strip() not in {"", "General"}
    }
    course_map = {c["course_id"]: c["course_name"] for c in courses if c.get("course_id") and c.get("course_name")}
    needed_topics = {
        (course_map.get(str(e.get("course_id", "")), ""), str(e.get("topic", "")).strip().lower())
        for e in estimates
        if str(e.get("course_id", "")).strip() in course_map and str(e.get("topic", "")).strip()
    }
    coverage_ok = needed_topics.issubset(covered_topics)

    total_estimated_minutes = 0
    for est in estimates:
        course_id = str(est.get("course_id", "")).strip()
        if course_id not in course_map:
            continue
        total_estimated_minutes += max(0, int(est.get("estimated_minutes", 0)))

    by_day: dict[str, int] = {}
    deadline_ok = True
    total_planned_minutes = 0
    for row in plan_rows:
        d = str(row.get("date", "")).strip()
        if not d:
            continue
        row_minutes = max(0, int(row.get("estimated_minutes", 0)))
        by_day[d] = by_day.get(d, 0) + row_minutes
        total_planned_minutes += row_minutes
        course_name = str(row.get("course", "")).strip()
        if course_name in course_midterms and date.fromisoformat(d) > course_midterms[course_name]:
            deadline_ok = False
    load_balance_ok = all(total <= daily_cap for total in by_day.values())
    total_available_minutes = len(required_dates) * max(0, int(daily_cap))
    capacity_shortfall_minutes = max(0, total_estimated_minutes - total_available_minutes)
    capacity_shortfall_detected = capacity_shortfall_minutes > 0

    reasons: list[str] = []
    if not coverage_ok:
        if capacity_shortfall_detected:
            reasons.append(
                "Full topic coverage is mathematically impossible under the current date window and daily cap."
            )
        else:
            reasons.append("Not all estimated topics are represented in the plan.")
    if not date_range_ok:
        reasons.append("Plan does not include every date from today through the last midterm.")
    if not load_balance_ok:
        reasons.append("One or more days exceed the configured daily study cap.")
    if not deadline_ok:
        reasons.append("One or more course tasks are scheduled after that course midterm date.")

    return (
        {
            "coverage_ok": coverage_ok,
            "date_range_ok": date_range_ok,
            "load_balance_ok": load_balance_ok,
            "deadline_ok": deadline_ok,
            "total_estimated_minutes": total_estimated_minutes,
            "total_planned_minutes": total_planned_minutes,
            "total_available_minutes": total_available_minutes,
            "capacity_shortfall_minutes": capacity_shortfall_minutes,
            "capacity_shortfall_detected": capacity_shortfall_detected,
        },
        reasons,
    )


def review_and_finalize_plan(
    session_id: str,
    daily_study_cap_minutes: int = 240,
    allow_auto_revision: bool = True,
    max_revision_rounds: int = 1,
) -> dict[str, Any]:
    state = _load_state(session_id)
    if not state.get("planning_state", {}).get("plan_rows"):
        build_schedule_plan(session_id=session_id, daily_study_cap_minutes=daily_study_cap_minutes)
        state = _load_state(session_id)

    validation_report, reasons = _validate_plan(state, daily_cap=daily_study_cap_minutes)
    rounds = 0
    cap = daily_study_cap_minutes

    while (
        reasons
        and allow_auto_revision
        and rounds < max_revision_rounds
        and not _is_capacity_limited_only(validation_report)
    ):
        rounds += 1
        _append_event(
            state,
            session_id=session_id,
            agent_name="PlanningReviewerAgent",
            event_type="revision",
            summary=f"Starting revision round {rounds} with {len(reasons)} issues.",
            artifact_refs=[f"revision_round:{rounds}"],
        )
        _save_state(session_id, state)
        if not validation_report.get("load_balance_ok", True):
            cap = min(480, cap + 60)
        build_schedule_plan(
            session_id=session_id,
            daily_study_cap_minutes=cap,
            force_reprocess=True,
        )
        state = _load_state(session_id)
        validation_report, reasons = _validate_plan(state, daily_cap=cap)

    if not reasons:
        result_type = "approved_plan"
    elif _is_capacity_limited_only(validation_report):
        result_type = "capacity_limited_plan"
    else:
        result_type = "needs_revision"
    state["status"] = "reviewing"
    state.setdefault("planning_state", {})["review"] = {
        "result_type": result_type,
        "revision_reasons": reasons,
        "validation_report": validation_report,
        "revision_rounds": rounds,
        "effective_daily_study_cap_minutes": cap,
    }
    _append_event(
        state,
        session_id=session_id,
        agent_name="PlanningReviewerAgent",
        event_type="review",
        summary=(
            f"Review verdict: {result_type}. "
            f"Rounds={rounds}, reasons={len(reasons)}."
        ),
        artifact_refs=[f"review:{result_type}"],
    )
    _save_state(session_id, state)
    return {
        "session_id": session_id,
        "result_type": result_type,
        "revision_reasons": reasons,
        "validation_report": validation_report,
        "revision_rounds": rounds,
        "effective_daily_study_cap_minutes": cap,
    }
