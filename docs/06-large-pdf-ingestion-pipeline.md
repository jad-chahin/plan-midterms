# Exam Study Planner - Step 6 Large PDF Ingestion Pipeline

## Implemented
- Session-scoped file registration and deduplication by `sha256 + size_bytes`.
- One-time upload persistence per session under:
  - `artifacts/sessions/<session_id>/files/`
  - `artifacts/sessions/<session_id>/state.json`
- Chunked PDF processing with `pypdf` using page windows (`max_pages_per_chunk`).
- Token-safe chunk input via `max_chars_per_chunk` cap.
- Gemini multi-call extraction per chunk with exponential retry/backoff.
- Aggregation of chunk outputs into normalized `course_topic_evidence`.
- ADK tool wiring into `IngestionAgent`:
  - `register_session_files`
  - `ingest_session_documents`
  - `read_ingestion_state`

## Files Added/Updated
- `exam_study_planner/ingestion.py`
- `exam_study_planner/tools.py`
- `exam_study_planner/agent.py`
- `exam_study_planner/settings.py`

## Tool Contracts
### `register_session_files`
- Inputs:
  - `session_id: str`
  - `files: list[{path, course_ids, is_shared}]`
- Behavior:
  - Validates PDF-only uploads.
  - Stores each file once in the session.
  - Reuses duplicates in same session by checksum.

### `ingest_session_documents`
- Inputs:
  - `session_id: str`
  - `max_pages_per_chunk: int` (default `20`)
  - `max_chars_per_chunk: int` (default `18000`)
  - `force_reprocess: bool` (default `false`)
- Behavior:
  - Splits PDFs into chunks.
  - Calls Gemini per chunk (or fallback if no API key).
  - Retries transient failures with exponential backoff.
  - Updates persistent ingestion progress and evidence.

### `read_ingestion_state`
- Input:
  - `session_id: str`
- Behavior:
  - Returns persisted state for reuse across agent invocations.

## Environment Options
- `INGESTION_MAX_CHUNK_PAGES` (default `20`)
- `INGESTION_MAX_CHUNK_CHARS` (default `18000`)
- `INGESTION_MAX_GEMINI_RETRIES` (default `5`)
- `INGESTION_RETRY_BASE_SECONDS` (default `1.2`)
- `EXAM_STUDY_PLANNER_ARTIFACTS_DIR` (default `artifacts`)

## Step 6 Definition of Done Check
- Upload once per session: implemented via `file_registry` + checksum dedupe.
- Persist across invocations: implemented via `state.json`.
- Handle very large PDFs safely: implemented via chunking + per-chunk calls.
- Token/rate-limit risk controls: implemented via char caps + retry/backoff.
