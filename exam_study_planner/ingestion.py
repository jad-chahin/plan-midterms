from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from pypdf import PdfReader

from .resilience import retry_with_backoff
from .settings import get_settings

SETTINGS = get_settings()


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _session_dir(session_id: str) -> Path:
    return SETTINGS.artifacts_dir / "sessions" / session_id


def _state_path(session_id: str) -> Path:
    return _session_dir(session_id) / "state.json"


def _default_state(session_id: str) -> dict[str, Any]:
    now = _now_iso()
    return {
        "session_id": session_id,
        "created_at": now,
        "updated_at": now,
        "status": "collecting_inputs",
        "user_inputs": {
            "courses": [],
        },
        "file_registry": {},
        "ingestion_state": {
            "files": {},
            "course_topic_evidence": [],
        },
        "events": [],
    }


def _load_state(session_id: str) -> dict[str, Any]:
    path = _state_path(session_id)
    if not path.exists():
        state = _default_state(session_id)
        _save_state(session_id, state)
        return state
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


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _normalize_date(raw: str) -> str:
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid date format, expected YYYY-MM-DD: {raw}") from exc
    return parsed.isoformat()


def _assert_future_or_today(midterm_date: str) -> None:
    parsed = date.fromisoformat(midterm_date)
    if parsed < date.today():
        raise ValueError(
            f"Midterm date must be today or future. Got {midterm_date}, today is {date.today().isoformat()}."
        )


def register_courses(session_id: str, courses: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Register/replace course metadata for a session.

    Each course item:
    {
      "course_id": "course_calc2",
      "course_name": "Calculus II",
      "midterm_date": "2026-02-21"
    }
    """
    if not courses:
        raise ValueError("At least one course is required.")

    state = _load_state(session_id)
    normalized: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for idx, item in enumerate(courses):
        course_id = str(item.get("course_id", "")).strip() or f"course_{idx + 1:03d}"
        course_name = str(item.get("course_name", "")).strip()
        if not course_name:
            raise ValueError("Course name is required.")
        midterm_date = _normalize_date(str(item.get("midterm_date", "")).strip())
        _assert_future_or_today(midterm_date)
        if course_id in seen_ids:
            raise ValueError(f"Duplicate course_id: {course_id}")
        seen_ids.add(course_id)
        normalized.append(
            {
                "course_id": course_id,
                "course_name": course_name,
                "midterm_date": midterm_date,
            }
        )

    state.setdefault("user_inputs", {})["courses"] = normalized
    _append_event(
        state,
        session_id=session_id,
        agent_name="CoordinatorAgent",
        event_type="handoff",
        summary=f"Registered {len(normalized)} courses.",
    )
    _save_state(session_id, state)
    return {"session_id": session_id, "courses": normalized}


def register_pdf_files(session_id: str, files: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Register and store PDF files once per session.

    Each file item:
    {
      "path": "absolute-or-relative-path.pdf",
      "course_ids": ["course_calc2"],
      "is_shared": false
    }
    """
    state = _load_state(session_id)
    session_files_dir = _session_dir(session_id) / "files"
    session_files_dir.mkdir(parents=True, exist_ok=True)
    registry = state.setdefault("file_registry", {})

    checksum_index = {
        (meta.get("sha256"), meta.get("size_bytes")): file_id
        for file_id, meta in registry.items()
    }

    registered: list[dict[str, Any]] = []
    reused: list[dict[str, Any]] = []

    for idx, entry in enumerate(files):
        input_path = Path(str(entry.get("path", ""))).expanduser().resolve()
        if not input_path.exists():
            raise FileNotFoundError(f"File not found: {input_path}")
        if input_path.suffix.lower() != ".pdf":
            raise ValueError(f"Only PDF files are supported: {input_path.name}")

        size_bytes = input_path.stat().st_size
        checksum = _sha256(input_path)
        existing_id = checksum_index.get((checksum, size_bytes))
        if existing_id:
            reused.append(
                {
                    "file_id": existing_id,
                    "filename": registry[existing_id]["filename"],
                    "reason": "duplicate_checksum_size",
                }
            )
            continue

        file_id = f"file_{len(registry) + 1:03d}"
        stored_name = f"{file_id}{input_path.suffix.lower()}"
        stored_path = session_files_dir / stored_name
        shutil.copy2(input_path, stored_path)

        file_meta = {
            "filename": input_path.name,
            "content_type": "application/pdf",
            "size_bytes": size_bytes,
            "storage_uri": str(stored_path),
            "sha256": checksum,
            "registration_status": "registered",
            "course_ids": sorted(set(entry.get("course_ids", []))),
            "is_shared": bool(entry.get("is_shared", False)),
        }
        registry[file_id] = file_meta
        checksum_index[(checksum, size_bytes)] = file_id
        registered.append({"file_id": file_id, "filename": input_path.name})

        state["ingestion_state"]["files"][file_id] = {
            "chunking": {
                "mode": "page_window",
                "max_pages_per_chunk": SETTINGS.max_chunk_pages,
                "total_chunks": 0,
            },
            "processed_chunks": 0,
            "failed_chunks": [],
            "status": "pending",
            "last_error": "",
            "chunk_results": [],
        }

    if registered:
        state["status"] = "ingesting"
    _append_event(
        state,
        session_id=session_id,
        agent_name="IngestionAgent",
        event_type="handoff",
        summary=f"Registered {len(registered)} files, reused {len(reused)} files.",
        artifact_refs=[item["file_id"] for item in registered],
    )
    _save_state(session_id, state)
    return {
        "session_id": session_id,
        "registered_files": registered,
        "reused_files": reused,
        "total_files_in_session": len(registry),
    }


def link_files_to_courses(session_id: str, mappings: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Update course mapping for already-registered files.

    Each mapping item:
    {
      "file_id": "file_001" or "filename": "calc_textbook.pdf",
      "course_ids": ["course_calc2"],
      "is_shared": false
    }
    """
    state = _load_state(session_id)
    registry = state.get("file_registry", {})
    if not registry:
        raise ValueError("No registered files found for this session.")
    if not mappings:
        raise ValueError("At least one mapping item is required.")

    by_filename = {meta.get("filename"): file_id for file_id, meta in registry.items()}
    updated: list[str] = []
    for item in mappings:
        file_id = str(item.get("file_id", "")).strip()
        if not file_id:
            filename = str(item.get("filename", "")).strip()
            file_id = by_filename.get(filename, "")
        if file_id not in registry:
            raise ValueError(f"Unknown file reference in mapping: {item}")

        course_ids = sorted(set(str(c).strip() for c in item.get("course_ids", []) if str(c).strip()))
        is_shared = bool(item.get("is_shared", False))
        if not course_ids and not is_shared:
            raise ValueError(
                f"File {file_id} must map to at least one course or be marked shared."
            )
        registry[file_id]["course_ids"] = course_ids
        registry[file_id]["is_shared"] = is_shared
        updated.append(file_id)

    _append_event(
        state,
        session_id=session_id,
        agent_name="IngestionAgent",
        event_type="handoff",
        summary=f"Linked {len(updated)} files to courses.",
        artifact_refs=sorted(set(updated)),
    )
    _save_state(session_id, state)
    return {"session_id": session_id, "updated_file_ids": sorted(set(updated))}


def _extract_pages_text(reader: PdfReader, page_start: int, page_end: int, max_chars: int) -> str:
    chunks: list[str] = []
    remaining = max_chars
    for page_index in range(page_start, page_end):
        text = reader.pages[page_index].extract_text() or ""
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        if len(text) > remaining:
            chunks.append(text[:remaining])
            break
        chunks.append(text)
        remaining -= len(text)
        if remaining <= 0:
            break
    return "\n".join(chunks)


def _fallback_extract_topics(chunk_text: str) -> list[dict[str, str]]:
    # Fallback for local runs without API key.
    candidates = re.findall(r"\b[A-Z][A-Za-z0-9\-]{3,}(?:\s+[A-Z][A-Za-z0-9\-]{3,}){0,3}\b", chunk_text)
    seen: set[str] = set()
    topics: list[dict[str, str]] = []
    for item in candidates:
        topic = item.strip()
        if topic in seen:
            continue
        seen.add(topic)
        topics.append({"topic": topic, "evidence_summary": "Extracted from PDF text chunk."})
        if len(topics) >= 8:
            break
    if not topics and chunk_text:
        topics = [{"topic": "General Review", "evidence_summary": "No explicit heading detected."}]
    return topics


def normalize_topic_label(topic: str) -> str:
    """
    Normalize topic string for de-duplication across chunk outputs.
    """
    normalized = re.sub(r"[^a-zA-Z0-9\s]", " ", topic.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _target_course_ids(meta: dict[str, Any], state: dict[str, Any]) -> list[str]:
    course_ids = list(meta.get("course_ids", []))
    if course_ids:
        return sorted(set(course_ids))
    if meta.get("is_shared", False):
        all_courses = [
            c.get("course_id")
            for c in state.get("user_inputs", {}).get("courses", [])
            if c.get("course_id")
        ]
        if all_courses:
            return sorted(set(all_courses))
    return ["shared"]


def _gemini_extract_topics(chunk_text: str) -> list[dict[str, str]]:
    if not SETTINGS.google_api_key:
        return _fallback_extract_topics(chunk_text)

    client = genai.Client(api_key=SETTINGS.google_api_key)
    prompt = (
        "You extract study topics from textbook/syllabus text. "
        "Return strict JSON array only. "
        "Each object must include keys: topic, evidence_summary. "
        "Keep evidence_summary <= 20 words.\n\n"
        f"TEXT:\n{chunk_text}"
    )

    def _call() -> list[dict[str, str]]:
        resp = client.models.generate_content(
            model=SETTINGS.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )
        raw = (resp.text or "").strip()
        raw = re.sub(r"^```json|^```|```$", "", raw, flags=re.MULTILINE).strip()
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return _fallback_extract_topics(chunk_text)
        normalized = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            topic = str(item.get("topic", "")).strip()
            evidence = str(item.get("evidence_summary", "")).strip()
            if topic:
                normalized.append(
                    {
                        "topic": topic[:180],
                        "evidence_summary": evidence[:240] or "Extracted topic evidence.",
                    }
                )
        return normalized or _fallback_extract_topics(chunk_text)

    try:
        return retry_with_backoff(
            _call,
            max_retries=SETTINGS.max_gemini_retries,
            base_seconds=SETTINGS.retry_base_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Gemini extraction failed after retries: {exc}") from exc


def _chunk_ranges(page_count: int, max_pages_per_chunk: int) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    start = 0
    while start < page_count:
        end = min(start + max_pages_per_chunk, page_count)
        ranges.append((start, end))
        start = end
    return ranges


def run_ingestion(
    session_id: str,
    max_pages_per_chunk: int | None = None,
    max_chars_per_chunk: int | None = None,
    force_reprocess: bool = False,
) -> dict[str, Any]:
    state = _load_state(session_id)
    state["status"] = "ingesting"
    max_pages = max_pages_per_chunk or SETTINGS.max_chunk_pages
    max_chars = max_chars_per_chunk or SETTINGS.max_chunk_chars

    all_topic_evidence: list[dict[str, Any]] = []
    warnings: list[str] = []
    file_registry = state.get("file_registry", {})

    for file_id, meta in file_registry.items():
        per_file_state = state["ingestion_state"]["files"].setdefault(
            file_id,
            {
                "chunking": {
                    "mode": "page_window",
                    "max_pages_per_chunk": max_pages,
                    "total_chunks": 0,
                },
                "processed_chunks": 0,
                "failed_chunks": [],
                "status": "pending",
                "last_error": "",
                "chunk_results": [],
            },
        )
        if per_file_state.get("status") == "complete" and not force_reprocess:
            all_topic_evidence.extend(per_file_state.get("topic_evidence", []))
            continue

        storage_uri = meta.get("storage_uri", "")
        pdf_path = Path(storage_uri)
        if not pdf_path.exists():
            warning = f"Missing stored file for {file_id}: {storage_uri}"
            warnings.append(warning)
            per_file_state["status"] = "failed"
            per_file_state["last_error"] = warning
            continue

        reader = PdfReader(str(pdf_path))
        ranges = _chunk_ranges(len(reader.pages), max_pages)
        per_file_state["chunking"] = {
            "mode": "page_window",
            "max_pages_per_chunk": max_pages,
            "total_chunks": len(ranges),
        }

        chunk_results = per_file_state.get("chunk_results", [])
        completed_ids = {item["chunk_id"] for item in chunk_results if "chunk_id" in item}
        if force_reprocess:
            chunk_results = []
            completed_ids = set()
            per_file_state["processed_chunks"] = 0
            per_file_state["failed_chunks"] = []

        topic_evidence_for_file: list[dict[str, Any]] = []
        for idx, (start, end) in enumerate(ranges):
            chunk_id = f"{file_id}:{idx}"
            if chunk_id in completed_ids:
                continue

            chunk_text = _extract_pages_text(reader, start, end, max_chars=max_chars)
            if not chunk_text:
                chunk_results.append(
                    {
                        "chunk_id": chunk_id,
                        "page_start": start + 1,
                        "page_end": end,
                        "topics": [],
                        "status": "empty",
                    }
                )
                per_file_state["processed_chunks"] = per_file_state.get("processed_chunks", 0) + 1
                continue

            try:
                topics = _gemini_extract_topics(chunk_text)
                chunk_results.append(
                    {
                        "chunk_id": chunk_id,
                        "page_start": start + 1,
                        "page_end": end,
                        "topics": topics,
                        "status": "complete",
                    }
                )
                per_file_state["processed_chunks"] = per_file_state.get("processed_chunks", 0) + 1
                for topic_item in topics:
                    topic_evidence_for_file.append(
                        {
                            "course_ids": _target_course_ids(meta, state),
                            "topic": topic_item["topic"],
                            "evidence_summary": topic_item["evidence_summary"],
                            "source_files": [file_id],
                            "source_chunks": [chunk_id],
                        }
                    )
                time.sleep(0.3)
            except Exception as exc:  # noqa: BLE001
                per_file_state.setdefault("failed_chunks", []).append(idx)
                per_file_state["status"] = "partial"
                per_file_state["last_error"] = str(exc)
                warnings.append(f"{file_id} chunk {idx} failed: {exc}")

        per_file_state["chunk_results"] = chunk_results
        total = per_file_state["chunking"]["total_chunks"]
        processed = per_file_state.get("processed_chunks", 0)
        if processed >= total and not per_file_state.get("failed_chunks"):
            per_file_state["status"] = "complete"
            per_file_state["last_error"] = ""
        elif processed > 0:
            per_file_state["status"] = "partial"
        per_file_state["topic_evidence"] = topic_evidence_for_file
        all_topic_evidence.extend(topic_evidence_for_file)

    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for item in all_topic_evidence:
        course_ids = item.get("course_ids") or ["shared"]
        for course_id in course_ids:
            normalized_topic = normalize_topic_label(item["topic"])
            if not normalized_topic:
                continue
            key = (course_id, normalized_topic)
            if key not in merged:
                merged[key] = {
                    "course_id": course_id,
                    "topic": item["topic"],
                    "normalized_topic": normalized_topic,
                    "evidence_summary": item["evidence_summary"],
                    "source_files": [],
                    "source_chunks": [],
                }
            merged_item = merged[key]
            merged_item["source_files"] = sorted(
                set(merged_item["source_files"] + item["source_files"])
            )
            merged_item["source_chunks"] = sorted(
                set(merged_item["source_chunks"] + item["source_chunks"])
            )
            if len(item.get("topic", "")) > len(merged_item.get("topic", "")):
                merged_item["topic"] = item["topic"]

    state["ingestion_state"]["course_topic_evidence"] = list(merged.values())
    _append_event(
        state,
        session_id=session_id,
        agent_name="IngestionAgent",
        event_type="complete",
        summary=(
            f"Processed {len(file_registry)} files into "
            f"{len(state['ingestion_state']['course_topic_evidence'])} topic evidence rows."
        ),
        artifact_refs=[f"topic_rows:{len(state['ingestion_state']['course_topic_evidence'])}"],
    )
    if warnings:
        _append_event(
            state,
            session_id=session_id,
            agent_name="IngestionAgent",
            event_type="error",
            summary=f"Ingestion completed with {len(warnings)} warnings.",
            artifact_refs=["warnings"],
        )
    _save_state(session_id, state)
    return {
        "session_id": session_id,
        "ingestion_status": "complete" if not warnings else "partial",
        "warnings": warnings,
        "course_topic_evidence_count": len(state["ingestion_state"]["course_topic_evidence"]),
        "files": {
            file_id: {
                "status": file_state.get("status", "pending"),
                "processed_chunks": file_state.get("processed_chunks", 0),
                "total_chunks": file_state.get("chunking", {}).get("total_chunks", 0),
            }
            for file_id, file_state in state["ingestion_state"]["files"].items()
        },
    }


def get_session_ingestion_state(session_id: str) -> dict[str, Any]:
    state = _load_state(session_id)
    return {
        "session_id": state["session_id"],
        "status": state["status"],
        "file_registry": state.get("file_registry", {}),
        "ingestion_state": state.get("ingestion_state", {}),
        "events": state.get("events", []),
    }
