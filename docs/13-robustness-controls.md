# Exam Study Planner - Step 13 Robustness Controls

## Implemented
- Added shared resilience utilities in `exam_study_planner/resilience.py`:
  - retryable error classification (`is_retryable_error`)
  - exponential backoff with jitter (`retry_with_backoff`)
- Integrated centralized retry handling for Gemini calls in:
  - `exam_study_planner/ingestion.py`
  - `exam_study_planner/estimation.py`
- Added stage-safe tool wrappers in `exam_study_planner/tools.py` for:
  - ingestion
  - estimation
  - planning
  - review
  - export

## Failure Handling Behavior
- On stage exceptions, tools return structured failure payload instead of
  uncaught crashes:
  - `status: failed`
  - `stage`
  - `error`
  - `retryable`
- Error events are persisted into collaboration trace (`event_type=error`) so
  session diagnostics remain visible in ADK UI.
- Ingestion keeps partial progress and emits warnings; completion with warnings
  also records an error-level trace event.

## Why This Meets Step 13
- Rate limits/transient model issues: handled with retry/backoff.
- Partial failures: ingestion continues per-file/per-chunk and records warning
  state without losing prior successful work.
- Recoverability: state remains persisted; downstream tools can inspect trace
  and retry stages with `force_reprocess`.
