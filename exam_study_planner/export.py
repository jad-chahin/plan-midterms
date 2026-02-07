from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .settings import get_settings

SETTINGS = get_settings()

CSV_COLUMNS = [
    "date",
    "course",
    "topic",
    "task_description",
    "estimated_minutes",
    "priority",
    "source_files",
    "status",
]


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


def _normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        source_files = row.get("source_files", [])
        if isinstance(source_files, list):
            source_files_value = ";".join(str(x) for x in source_files)
        else:
            source_files_value = str(source_files)
        normalized.append(
            {
                "date": str(row.get("date", "")).strip(),
                "course": str(row.get("course", "")).strip(),
                "topic": str(row.get("topic", "")).strip(),
                "task_description": str(row.get("task_description", "")).strip(),
                "estimated_minutes": int(row.get("estimated_minutes", 0)),
                "priority": str(row.get("priority", "medium")).strip().lower() or "medium",
                "source_files": source_files_value,
                "status": str(row.get("status", "planned")).strip() or "planned",
            }
        )
    normalized.sort(key=lambda r: (r["date"], r["course"], r["topic"], r["task_description"]))
    return normalized


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in CSV_COLUMNS})


def _coverage_lines(rows: list[dict[str, Any]], estimates: list[dict[str, Any]], courses: list[dict[str, Any]]) -> list[str]:
    planned = {}
    for row in rows:
        c = row["course"]
        planned[c] = planned.get(c, 0) + 1

    est_by_course = {}
    course_id_to_name = {c.get("course_id"): c.get("course_name") for c in courses}
    for est in estimates:
        c_name = course_id_to_name.get(est.get("course_id"), "")
        if not c_name:
            continue
        est_by_course[c_name] = est_by_course.get(c_name, 0) + 1

    lines: list[str] = []
    for course in sorted(course_id_to_name.values()):
        if not course:
            continue
        est_count = est_by_course.get(course, 0)
        plan_count = planned.get(course, 0)
        percent = 100 if est_count == 0 else int(min(100, round((plan_count / max(1, est_count)) * 100)))
        lines.append(f"- {course}: {percent}% estimated-topic representation in plan rows.")
    return lines


def _write_markdown(
    path: Path,
    rows: list[dict[str, Any]],
    courses: list[dict[str, Any]],
    estimates: list[dict[str, Any]],
    warnings: list[str],
) -> None:
    lines: list[str] = []
    lines.append("# Exam Study Plan")
    lines.append("")
    lines.append("## Student Inputs")
    if courses:
        course_names = ", ".join(c.get("course_name", "") for c in courses if c.get("course_name"))
        midterms = ", ".join(c.get("midterm_date", "") for c in courses if c.get("midterm_date"))
        lines.append(f"- Courses: {course_names}")
        lines.append(f"- Midterms: {midterms}")
    else:
        lines.append("- Courses: (none)")
    lines.append("")

    lines.append("## Planning Assumptions")
    lines.append("- Study window starts at current session date and ends at last midterm date.")
    lines.append("- Topic effort is based on estimation output and split into daily blocks.")
    if warnings:
        for w in warnings:
            lines.append(f"- Warning: {w}")
    lines.append("")

    lines.append("## Day-by-Day Plan")
    lines.append("| Date | Course | Topic | Task | Minutes |")
    lines.append("|---|---|---|---|---|")
    for row in rows:
        lines.append(
            f"| {row['date']} | {row['course']} | {row['topic']} | {row['task_description']} | {row['estimated_minutes']} |"
        )
    lines.append("")

    lines.append("## Coverage Check by Course")
    lines.extend(_coverage_lines(rows=rows, estimates=estimates, courses=courses))
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def export_study_plan_outputs(session_id: str, overwrite: bool = True) -> dict[str, Any]:
    state = _load_state(session_id)
    plan_rows = state.get("planning_state", {}).get("plan_rows", [])
    if not plan_rows:
        raise ValueError("No planning_state.plan_rows found. Run planning/review first.")

    normalized_rows = _normalize_rows(plan_rows)
    outputs_dir = _session_dir(session_id) / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    csv_path = outputs_dir / "study_plan.csv"
    md_path = outputs_dir / "study_plan.md"
    if not overwrite and (csv_path.exists() or md_path.exists()):
        raise ValueError("Output files already exist and overwrite=False.")

    _write_csv(csv_path, normalized_rows)
    _write_markdown(
        md_path,
        rows=normalized_rows,
        courses=state.get("user_inputs", {}).get("courses", []),
        estimates=state.get("estimation_state", {}).get("topic_estimates", []),
        warnings=state.get("planning_state", {}).get("warnings", []),
    )

    state.setdefault("artifacts", {})
    state["artifacts"]["csv_path"] = str(csv_path)
    state["artifacts"]["markdown_path"] = str(md_path)
    state["status"] = "completed"
    _append_event(
        state,
        session_id=session_id,
        agent_name="CoordinatorAgent",
        event_type="complete",
        summary="Exported final study plan artifacts (CSV and Markdown).",
        artifact_refs=[str(csv_path), str(md_path)],
    )
    _save_state(session_id, state)
    return {
        "session_id": session_id,
        "csv_path": str(csv_path),
        "markdown_path": str(md_path),
        "row_count": len(normalized_rows),
    }


def read_output_artifacts(session_id: str) -> dict[str, Any]:
    state = _load_state(session_id)
    artifacts = state.get("artifacts", {})
    csv_path = artifacts.get("csv_path", "")
    md_path = artifacts.get("markdown_path", "")
    csv_exists = bool(csv_path) and Path(csv_path).exists()
    md_exists = bool(md_path) and Path(md_path).exists()
    return {
        "session_id": session_id,
        "artifacts": {
            "csv_path": csv_path,
            "markdown_path": md_path,
            "csv_exists": csv_exists,
            "markdown_exists": md_exists,
        },
    }
