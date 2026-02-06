from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import io
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import google.generativeai as genai
from dotenv import load_dotenv
from pypdf import PdfReader

OUTPUT_DIR = Path("outputs")
DEFAULT_MODEL = "gemini-2.0-flash"
STATE_DOCS = "app.documents"
STATE_ESTIMATES = "app.estimates"
STATE_PLAN = "app.plan"

load_dotenv()


@dataclass
class DocumentSummary:
    filename: str
    course: str
    topics: List[str]
    summary: str
    pages: int
    word_count: int


def _ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _gemini_available() -> bool:
    return bool(os.getenv("GOOGLE_API_KEY"))


def _gemini_model() -> Optional[genai.GenerativeModel]:
    if not _gemini_available():
        return None
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    return genai.GenerativeModel(DEFAULT_MODEL)


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = text[start : end + 1]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            return None
    return None


def _call_gemini_json(prompt: str) -> Optional[Dict[str, Any]]:
    model = _gemini_model()
    if model is None:
        return None
    response = model.generate_content(
        prompt,
        generation_config={"response_mime_type": "application/json"},
    )
    text = response.text or ""
    return _extract_json(text)


def _get_state(tool_context: Any) -> Any:
    if hasattr(tool_context, "state"):
        return tool_context.state
    context = getattr(tool_context, "context", None)
    if context is not None and hasattr(context, "state"):
        return context.state
    session = getattr(tool_context, "session_state", None)
    if session is None:
        session = {}
        setattr(tool_context, "session_state", session)
    return session


def _state_get(state: Any, key: str, default: Any) -> Any:
    try:
        return state.get(key, default)
    except AttributeError:
        try:
            return state[key]
        except Exception:
            return default


def _state_set(state: Any, key: str, value: Any) -> None:
    try:
        state[key] = value
    except Exception:
        try:
            state.set(key, value)
        except Exception:
            pass


def _list_artifacts(tool_context: Any) -> List[Any]:
    if hasattr(tool_context, "list_artifacts"):
        return tool_context.list_artifacts()
    artifacts = getattr(tool_context, "artifacts", None)
    if artifacts is None:
        return []
    if isinstance(artifacts, dict):
        return list(artifacts.values())
    return list(artifacts)


def _get_artifact(tool_context: Any, artifact_name: str) -> Any:
    if hasattr(tool_context, "get_artifact"):
        return tool_context.get_artifact(artifact_name)
    artifacts = _list_artifacts(tool_context)
    for artifact in artifacts:
        if getattr(artifact, "name", None) == artifact_name:
            return artifact
    raise KeyError(f"Artifact not found: {artifact_name}")


def _artifact_path(artifact: Any) -> Path:
    for attr in ("path", "local_path", "uri"):
        value = getattr(artifact, attr, None)
        if value:
            return Path(value)
    raise ValueError("Artifact has no usable path")


def _load_artifact_bytes(tool_context: Any, artifact_name: str) -> Optional[bytes]:
    if hasattr(tool_context, "load_artifact"):
        data = tool_context.load_artifact(artifact_name)
        if isinstance(data, (bytes, bytearray)):
            return bytes(data)
        if hasattr(data, "read"):
            return data.read()
        if hasattr(data, "content"):
            return data.content
    return None


def _extract_topics(text: str, limit: int = 20) -> List[str]:
    topics = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        lower = line.lower()
        if lower.startswith("chapter") or lower.startswith("topic"):
            topics.append(line[:120])
        if len(topics) >= limit:
            break
    return topics


def _normalize_topics(topics: List[str]) -> List[str]:
    seen = set()
    normalized = []
    for topic in topics:
        cleaned = " ".join(str(topic).split()).strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(cleaned)
    return normalized


def list_uploaded_documents(tool_context: Any) -> Dict[str, Any]:
    """
    List files uploaded in the current ADK session.
    The ADK UI/CLI provides artifacts; this returns their metadata.
    """
    try:
        artifacts = _list_artifacts(tool_context)
    except Exception as exc:  # pragma: no cover - depends on ADK runtime
        return {"error": f"Failed to list artifacts: {exc}"}

    files = []
    for artifact in artifacts:
        files.append(
            {
                "name": artifact.name,
                "mime_type": artifact.mime_type,
                "uri": getattr(artifact, "uri", None),
            }
        )

    state = _get_state(tool_context)
    cached = _state_get(state, STATE_DOCS, {})
    return {"files": files, "cached_documents": list(cached.keys())}


def ingest_pdf(
    tool_context: Any,
    artifact_name: str,
    course: str,
    topics_hint: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Extract text from a PDF artifact and store a simple summary in session state.
    """
    state = _get_state(tool_context)
    documents = _state_get(state, STATE_DOCS, {})
    if artifact_name in documents:
        return {"status": "cached", "document": documents[artifact_name]}

    try:
        data = _load_artifact_bytes(tool_context, artifact_name)
        if data is None:
            artifact = _get_artifact(tool_context, artifact_name)
            local_path = _artifact_path(artifact)
            reader = PdfReader(str(local_path))
        else:
            reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # pragma: no cover - depends on ADK runtime
        return {"error": f"Unable to access artifact '{artifact_name}': {exc}"}

    text_chunks = []
    for page in reader.pages:
        text_chunks.append(page.extract_text() or "")
    full_text = "\n".join(text_chunks)

    topics = topics_hint or _extract_topics(full_text)
    summary = full_text[:2000].strip()
    word_count = len(full_text.split())

    if _gemini_available():
        prompt = (
            "Return JSON only. No prose. Schema:\n"
            "{\n"
            "  \"summary\": \"string (<=120 words)\",\n"
            "  \"topics\": [\"short topic strings\"]\n"
            "}\n"
            f"Course: {course}\n"
            "If topics are unclear, infer likely sections. Use 5-20 topics.\n"
            "PDF excerpt:\n"
            f"{summary}\n"
        )
        gemini = _call_gemini_json(prompt)
        if gemini:
            summary = str(gemini.get("summary", summary)).strip() or summary
            topics = gemini.get("topics", topics) or topics

    topics = _normalize_topics(topics)
    summary_obj = DocumentSummary(
        filename=artifact_name,
        course=course,
        topics=topics,
        summary=summary,
        pages=len(reader.pages),
        word_count=word_count,
    )

    documents[artifact_name] = summary_obj.__dict__
    _state_set(state, STATE_DOCS, documents)

    return {"status": "ok", "document": summary_obj.__dict__}


def estimate_topic_load(
    tool_context: Any,
    course: str,
    topics: List[str],
) -> Dict[str, Any]:
    """
    Estimate study time per topic using Gemini when available.
    """
    state = _get_state(tool_context)
    if not topics:
        documents = _state_get(state, STATE_DOCS, {})
        for doc in documents.values():
            if doc.get("course") == course:
                topics = doc.get("topics", [])
                break
    topics = _normalize_topics(topics)

    estimates = []
    if _gemini_available() and topics:
        prompt = (
            "Return JSON only. No prose. Schema:\n"
            "{\n"
            "  \"estimates\": [\n"
            "    {\"topic\": \"string\", \"hours\": number}\n"
            "  ]\n"
            "}\n"
            f"Course: {course}\n"
            "Assume 2-3 weeks until exam and a student-level workload.\n"
            "Hours must be numeric (can be decimals).\n"
            f"Topics: {topics}\n"
        )
        gemini = _call_gemini_json(prompt)
        if gemini and "estimates" in gemini:
            for item in gemini["estimates"]:
                topic = str(item.get("topic", "")).strip()
                hours = item.get("hours", 2)
                if topic:
                    try:
                        hours_value = float(hours)
                    except (TypeError, ValueError):
                        hours_value = 2.0
                    estimates.append(
                        {"course": course, "topic": topic, "hours": hours_value}
                    )

    if not estimates:
        for topic in topics:
            estimates.append({"course": course, "topic": topic, "hours": 2})

    stored = _state_get(state, STATE_ESTIMATES, [])
    stored.extend(estimates)
    _state_set(state, STATE_ESTIMATES, stored)

    return {"status": "ok", "estimates": estimates}


def build_plan(
    tool_context: Any,
    start_date: str,
    end_date: str,
) -> Dict[str, Any]:
    """
    Build a naive day-by-day plan using stored estimates.
    """
    state = _get_state(tool_context)
    estimates = _state_get(state, STATE_ESTIMATES, [])
    if not estimates:
        return {"error": "No topic estimates found. Run workload estimation first."}

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    total_days = (end - start).days + 1
    if total_days <= 0:
        return {"error": "End date must be after start date."}

    plan = []
    idx = 0
    for day_offset in range(total_days):
        current_date = start.fromordinal(start.toordinal() + day_offset)
        if idx >= len(estimates):
            break
        item = estimates[idx]
        plan.append(
            {
                "date": current_date.isoformat(),
                "course": item["course"],
                "topic": item["topic"],
                "estimated_time": f'{item["hours"]}h',
                "notes": "",
            }
        )
        idx += 1

    _state_set(state, STATE_PLAN, plan)
    return {"status": "ok", "plan": plan}


def export_plan(
    tool_context: Any,
    format: str = "markdown",
    filename: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Export the current plan to outputs/ as Markdown or CSV.
    """
    state = _get_state(tool_context)
    plan = _state_get(state, STATE_PLAN, [])
    if not plan:
        return {"error": "No plan found. Build a plan first."}

    _ensure_output_dir()
    valid = validate_plan(tool_context)
    if valid.get("status") != "ok":
        return valid

    if format.lower() == "csv":
        name = filename or "study_plan.csv"
        path = OUTPUT_DIR / name
        headers = ["Date", "Course", "Topic", "Estimated Time", "Notes"]
        lines = [",".join(headers)]
        for row in plan:
            lines.append(
                ",".join(
                    [
                        row["date"],
                        row["course"],
                        row["topic"],
                        row["estimated_time"],
                        row["notes"],
                    ]
                )
            )
        path.write_text("\n".join(lines), encoding="utf-8")
    else:
        name = filename or "study_plan.md"
        path = OUTPUT_DIR / name
        lines = [
            "| Date | Course | Topic | Estimated Time | Notes |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in plan:
            lines.append(
                f'| {row["date"]} | {row["course"]} | {row["topic"]} | {row["estimated_time"]} | {row["notes"]} |'
            )
        path.write_text("\n".join(lines), encoding="utf-8")

    return {"status": "ok", "path": str(path)}


def validate_plan(tool_context: Any) -> Dict[str, Any]:
    """
    Validate the plan schema and normalize required fields.
    """
    state = _get_state(tool_context)
    plan = _state_get(state, STATE_PLAN, [])
    if not plan:
        return {"error": "No plan found. Build a plan first."}

    required = ["date", "course", "topic", "estimated_time", "notes"]
    errors = []
    normalized = []
    for idx, row in enumerate(plan, start=1):
        missing = [key for key in required if key not in row]
        if missing:
            errors.append(f"Row {idx} missing fields: {', '.join(missing)}")
            continue
        normalized.append(
            {
                "date": str(row["date"]).strip(),
                "course": str(row["course"]).strip(),
                "topic": str(row["topic"]).strip(),
                "estimated_time": str(row["estimated_time"]).strip(),
                "notes": str(row["notes"]).strip(),
            }
        )

    if errors:
        return {"error": "Plan validation failed.", "details": errors}

    _state_set(state, STATE_PLAN, normalized)
    return {"status": "ok", "rows": len(normalized)}
