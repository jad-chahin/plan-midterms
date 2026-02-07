from __future__ import annotations

import re
from typing import Any

from .collaboration import read_collaboration_trace, record_collaboration_event
from .estimation import estimate_workload, get_session_estimation_state
from .export import export_study_plan_outputs, read_output_artifacts
from .ingestion import (
    get_session_ingestion_state,
    link_files_to_courses,
    register_courses,
    register_pdf_files,
    run_ingestion,
)
from .planning import build_schedule_plan, get_session_planning_state
from .review import review_and_finalize_plan
from .resilience import is_retryable_error


def register_session_courses(session_id: str, courses: list[dict[str, Any]]) -> dict[str, Any]:
    """Persist course IDs/names/midterm dates for the session."""
    return register_courses(session_id=session_id, courses=courses)


def register_session_files(session_id: str, files: list[dict[str, Any]]) -> dict[str, Any]:
    """Register PDF files once for a session and persist storage references."""
    return register_pdf_files(session_id=session_id, files=files)


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
    return value or "course"


def _course_tokens(course_name: str) -> set[str]:
    parts = re.findall(r"[a-zA-Z0-9]+", course_name.lower())
    return {p for p in parts if len(p) >= 4}


def _auto_mappings_from_registered_files(
    registered_files: list[dict[str, Any]],
    course_defs: list[dict[str, str]],
) -> list[dict[str, Any]]:
    course_token_map = {
        c["course_id"]: _course_tokens(c["course_name"])
        for c in course_defs
    }
    mappings: list[dict[str, Any]] = []
    for f in registered_files:
        filename = str(f.get("filename", "")).lower()
        file_id = str(f.get("file_id", "")).strip()
        if not file_id:
            continue
        matched_course_ids: list[str] = []
        for course_id, tokens in course_token_map.items():
            if any(tok in filename for tok in tokens):
                matched_course_ids.append(course_id)
        if matched_course_ids:
            mappings.append(
                {
                    "file_id": file_id,
                    "course_ids": sorted(set(matched_course_ids)),
                    "is_shared": False,
                }
            )
        else:
            mappings.append(
                {
                    "file_id": file_id,
                    "course_ids": [],
                    "is_shared": True,
                }
            )
    return mappings


def run_simple_study_planner(
    session_id: str,
    course_names: list[str],
    midterm_dates: list[str],
    daily_study_cap_minutes: int = 240,
    file_paths: list[str] | None = None,
) -> dict[str, Any]:
    """
    One-shot simplified pipeline runner.

    One-shot simplified pipeline runner using local filesystem PDF paths.
    """
    if not course_names:
        raise ValueError("course_names must contain at least one course.")
    if len(course_names) != len(midterm_dates):
        raise ValueError("course_names and midterm_dates must have the same length.")

    course_defs: list[dict[str, str]] = []
    used_ids: set[str] = set()
    for idx, (name, midterm) in enumerate(zip(course_names, midterm_dates, strict=True)):
        course_name = str(name).strip()
        if not course_name:
            raise ValueError(f"course_names[{idx}] is empty.")
        base_id = _slug(course_name)
        course_id = base_id
        suffix = 2
        while course_id in used_ids:
            course_id = f"{base_id}_{suffix}"
            suffix += 1
        used_ids.add(course_id)
        course_defs.append(
            {
                "course_id": course_id,
                "course_name": course_name,
                "midterm_date": str(midterm).strip(),
            }
        )

    register_session_courses(session_id=session_id, courses=course_defs)

    if not file_paths:
        raise ValueError("file_paths is required and must include at least one PDF path.")
    reg = register_session_files(
        session_id=session_id,
        files=[{"path": p, "course_ids": [], "is_shared": False} for p in file_paths],
    )
    registered_files: list[dict[str, Any]] = list(reg.get("registered_files", []))
    reused_files: list[dict[str, Any]] = list(reg.get("reused_files", []))

    all_files_for_mapping = []
    all_files_for_mapping.extend(registered_files)
    all_files_for_mapping.extend(reused_files)
    mappings = _auto_mappings_from_registered_files(
        registered_files=all_files_for_mapping,
        course_defs=course_defs,
    )
    map_result = map_session_files_to_courses(session_id=session_id, mappings=mappings)

    ingestion = ingest_session_documents(session_id=session_id)
    estimation = estimate_session_workload(session_id=session_id)
    planning = build_session_study_plan(
        session_id=session_id,
        daily_study_cap_minutes=daily_study_cap_minutes,
    )
    review = review_session_plan(
        session_id=session_id,
        daily_study_cap_minutes=daily_study_cap_minutes,
        allow_auto_revision=True,
        max_revision_rounds=1,
    )
    export_info = export_session_study_plan(session_id=session_id, overwrite=True)
    outputs = read_session_output_artifacts(session_id=session_id)

    return {
        "session_id": session_id,
        "courses": course_defs,
        "registered_files": registered_files,
        "reused_files": reused_files,
        "mappings": mappings,
        "mapping_result": map_result,
        "ingestion": ingestion,
        "estimation": estimation,
        "planning": planning,
        "review": review,
        "export": export_info,
        "outputs": outputs,
    }


def map_session_files_to_courses(session_id: str, mappings: list[dict[str, Any]]) -> dict[str, Any]:
    """Map registered files to one or more courses, or mark files as shared."""
    return link_files_to_courses(session_id=session_id, mappings=mappings)


def ingest_session_documents(
    session_id: str,
    max_pages_per_chunk: int = 20,
    max_chars_per_chunk: int = 18000,
    force_reprocess: bool = False,
) -> dict[str, Any]:
    """Process registered PDFs in chunks and extract topic evidence."""
    try:
        return run_ingestion(
            session_id=session_id,
            max_pages_per_chunk=max_pages_per_chunk,
            max_chars_per_chunk=max_chars_per_chunk,
            force_reprocess=force_reprocess,
        )
    except Exception as exc:  # noqa: BLE001
        try:
            record_collaboration_event(
                session_id=session_id,
                agent_name="IngestionAgent",
                event_type="error",
                summary=f"Ingestion failed: {exc}",
                artifact_refs=["ingestion"],
            )
        except Exception:  # noqa: BLE001
            pass
        return {
            "session_id": session_id,
            "status": "failed",
            "stage": "ingestion",
            "error": str(exc),
            "retryable": is_retryable_error(exc),
        }


def read_ingestion_state(session_id: str) -> dict[str, Any]:
    """Read session ingestion state for reuse across agent invocations."""
    return get_session_ingestion_state(session_id=session_id)


def estimate_session_workload(
    session_id: str,
    min_minutes: int = 25,
    max_minutes: int = 240,
    force_reprocess: bool = False,
) -> dict[str, Any]:
    """Estimate topic-level study workload from normalized ingestion evidence."""
    try:
        return estimate_workload(
            session_id=session_id,
            min_minutes=min_minutes,
            max_minutes=max_minutes,
            force_reprocess=force_reprocess,
        )
    except Exception as exc:  # noqa: BLE001
        try:
            record_collaboration_event(
                session_id=session_id,
                agent_name="EstimationAgent",
                event_type="error",
                summary=f"Estimation failed: {exc}",
                artifact_refs=["estimation"],
            )
        except Exception:  # noqa: BLE001
            pass
        return {
            "session_id": session_id,
            "status": "failed",
            "stage": "estimation",
            "error": str(exc),
            "retryable": is_retryable_error(exc),
        }


def read_estimation_state(session_id: str) -> dict[str, Any]:
    """Read persisted estimation state for downstream planning agent use."""
    return get_session_estimation_state(session_id=session_id)


def build_session_study_plan(
    session_id: str,
    daily_study_cap_minutes: int = 240,
    min_block_minutes: int = 30,
    max_block_minutes: int = 90,
    force_reprocess: bool = False,
) -> dict[str, Any]:
    """Build day-by-day study allocations from today through the last midterm."""
    try:
        return build_schedule_plan(
            session_id=session_id,
            daily_study_cap_minutes=daily_study_cap_minutes,
            min_block_minutes=min_block_minutes,
            max_block_minutes=max_block_minutes,
            force_reprocess=force_reprocess,
        )
    except Exception as exc:  # noqa: BLE001
        try:
            record_collaboration_event(
                session_id=session_id,
                agent_name="PlanningReviewerAgent",
                event_type="error",
                summary=f"Planning failed: {exc}",
                artifact_refs=["planning"],
            )
        except Exception:  # noqa: BLE001
            pass
        return {
            "session_id": session_id,
            "status": "failed",
            "stage": "planning",
            "error": str(exc),
            "retryable": is_retryable_error(exc),
        }


def read_planning_state(session_id: str) -> dict[str, Any]:
    """Read persisted planning_state rows for final export/review."""
    return get_session_planning_state(session_id=session_id)


def review_session_plan(
    session_id: str,
    daily_study_cap_minutes: int = 240,
    allow_auto_revision: bool = True,
    max_revision_rounds: int = 1,
) -> dict[str, Any]:
    """Validate plan and return approved_plan, capacity_limited_plan, or needs_revision."""
    try:
        return review_and_finalize_plan(
            session_id=session_id,
            daily_study_cap_minutes=daily_study_cap_minutes,
            allow_auto_revision=allow_auto_revision,
            max_revision_rounds=max_revision_rounds,
        )
    except Exception as exc:  # noqa: BLE001
        try:
            record_collaboration_event(
                session_id=session_id,
                agent_name="PlanningReviewerAgent",
                event_type="error",
                summary=f"Review failed: {exc}",
                artifact_refs=["review"],
            )
        except Exception:  # noqa: BLE001
            pass
        return {
            "session_id": session_id,
            "status": "failed",
            "stage": "review",
            "error": str(exc),
            "retryable": is_retryable_error(exc),
        }


def record_session_collaboration_event(
    session_id: str,
    agent_name: str,
    event_type: str,
    summary: str,
    artifact_refs: list[str] | None = None,
) -> dict[str, Any]:
    """Record an explicit collaboration event for ADK UI trace visibility."""
    return record_collaboration_event(
        session_id=session_id,
        agent_name=agent_name,
        event_type=event_type,
        summary=summary,
        artifact_refs=artifact_refs,
    )


def read_session_collaboration_trace(
    session_id: str,
    limit: int = 100,
    event_types: list[str] | None = None,
) -> dict[str, Any]:
    """Read structured collaboration trace across all agents for a session."""
    return read_collaboration_trace(
        session_id=session_id,
        limit=limit,
        event_types=event_types,
    )


def export_session_study_plan(
    session_id: str,
    overwrite: bool = True,
) -> dict[str, Any]:
    """Export deterministic study plan outputs to CSV and Markdown files."""
    try:
        return export_study_plan_outputs(session_id=session_id, overwrite=overwrite)
    except Exception as exc:  # noqa: BLE001
        try:
            record_collaboration_event(
                session_id=session_id,
                agent_name="CoordinatorAgent",
                event_type="error",
                summary=f"Export failed: {exc}",
                artifact_refs=["export"],
            )
        except Exception:  # noqa: BLE001
            pass
        return {
            "session_id": session_id,
            "status": "failed",
            "stage": "export",
            "error": str(exc),
            "retryable": is_retryable_error(exc),
        }


def read_session_output_artifacts(session_id: str) -> dict[str, Any]:
    """Read exported artifact paths/existence for the current session."""
    return read_output_artifacts(session_id=session_id)
