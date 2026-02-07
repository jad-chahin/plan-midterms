# Exam Study Planner - Session State Management

## 1. Purpose
Define how user/session data is stored and reused so:
- files are uploaded once per session,
- state persists across multiple agent invocations,
- and all agents operate on a shared, consistent session context.

This document is the source-of-truth for step 3.

## 2. Scope
This state model covers one active user session in ADK UI/CLI and includes:
- input metadata,
- document ingestion progress,
- extracted content,
- planning artifacts,
- and output file references.

Out of scope:
- long-term cross-session storage.
- multi-user tenancy and auth design.

## 3. Session Identity
- `session_id`: unique ID generated at session start.
- `created_at`: ISO timestamp.
- `updated_at`: ISO timestamp updated on every state write.
- `status`: `created|collecting_inputs|ingesting|estimating|planning|reviewing|completed|failed`.

All agent payloads must include `session_id`.

## 4. Canonical Session State Schema
```json
{
  "session_id": "string",
  "created_at": "2026-02-07T18:15:00Z",
  "updated_at": "2026-02-07T18:25:00Z",
  "status": "collecting_inputs",
  "user_inputs": {
    "timezone": "America/Los_Angeles",
    "courses": [
      {
        "course_id": "course_calc2",
        "course_name": "Calculus II",
        "midterm_date": "2026-02-21"
      }
    ],
    "shared_constraints": {
      "max_minutes_per_day": 240,
      "preferred_rest_day": "Sunday"
    }
  },
  "file_registry": {
    "file_001": {
      "filename": "calc_textbook.pdf",
      "content_type": "application/pdf",
      "size_bytes": 52300111,
      "storage_uri": "sessions/session_abc/files/file_001.pdf",
      "sha256": "string",
      "upload_status": "uploaded",
      "course_ids": ["course_calc2"],
      "is_shared": false
    }
  },
  "ingestion_state": {
    "files": {
      "file_001": {
        "chunking": {
          "mode": "page_window",
          "max_pages_per_chunk": 20,
          "total_chunks": 42
        },
        "processed_chunks": 40,
        "failed_chunks": [5],
        "status": "partial",
        "last_error": "429 rate limit"
      }
    },
    "course_topic_evidence": [
      {
        "course_id": "course_calc2",
        "topic": "Integration by Parts",
        "evidence_summary": "Technique + common error patterns",
        "source_files": ["file_001"],
        "source_chunks": ["file_001:12", "file_001:13"]
      }
    ]
  },
  "estimation_state": {
    "topic_estimates": [
      {
        "course_id": "course_calc2",
        "topic": "Integration by Parts",
        "estimated_minutes": 90,
        "priority": "high",
        "confidence": 0.84
      }
    ],
    "uncertainty_flags": []
  },
  "planning_state": {
    "plan_version": 2,
    "last_midterm_date": "2026-02-26",
    "plan_rows": [
      {
        "date": "2026-02-08",
        "course": "Calculus II",
        "topic": "Integration by Parts",
        "task_description": "Practice set A",
        "estimated_minutes": 90,
        "priority": "high",
        "source_files": ["calc_textbook.pdf"],
        "status": "planned"
      }
    ],
    "review": {
      "result_type": "approved_plan|capacity_limited_plan|needs_revision",
      "revision_reasons": [],
      "validation_report": {
        "coverage_ok": true,
        "date_range_ok": true,
        "load_balance_ok": true
      }
    }
  },
  "artifacts": {
    "markdown_path": "sessions/session_abc/outputs/study_plan.md",
    "csv_path": "sessions/session_abc/outputs/study_plan.csv"
  },
  "events": [
    {
      "timestamp": "2026-02-07T18:20:00Z",
      "agent_name": "IngestionAgent",
      "event_type": "handoff",
      "summary": "40/42 chunks processed for file_001"
    }
  ]
}
```

## 5. Persistence Rules
- Session state is the single mutable source of truth.
- Agent-local temporary data is not authoritative until written to session state.
- Every successful agent stage writes a checkpoint.
- File uploads are immutable within session after `upload_status=uploaded`.
- Re-planning increments `planning_state.plan_version`; previous plan can be retained as history if needed.

## 6. Lifecycle Transitions
Allowed transitions:
1. `created` -> `collecting_inputs`
2. `collecting_inputs` -> `ingesting`
3. `ingesting` -> `estimating`
4. `estimating` -> `planning`
5. `planning` -> `reviewing`
6. `reviewing` -> `planning` (revision loop) or `completed`
7. `any` -> `failed`

Transition guard rules:
- `collecting_inputs` cannot exit until each course has a midterm date.
- `ingesting` cannot exit until each required file is `complete` or explicitly marked `partial` with warning.
- `planning` cannot exit until all calendar days from start date to last midterm are represented in `plan_rows`.

## 7. Agent Read/Write Ownership
- `CoordinatorAgent`
  - Reads: all.
  - Writes: `status`, orchestration-level checkpoints, final `artifacts`.
- `IngestionAgent`
  - Reads: `user_inputs`, `file_registry`.
  - Writes: `ingestion_state`, ingestion warnings/events.
- `EstimationAgent`
  - Reads: `ingestion_state.course_topic_evidence`.
  - Writes: `estimation_state`.
- `PlanningReviewerAgent`
  - Reads: `user_inputs`, `estimation_state`.
  - Writes: `planning_state`, review verdicts.

## 8. Idempotency and Resume
- Upload idempotency key: `sha256 + size_bytes`.
- Chunk-processing idempotency key: `file_id + chunk_index`.
- Re-running ingestion or estimation should overwrite stale partial outputs for the same version boundary.
- Resume behavior:
  - On restart, agents read latest checkpoint and continue from unprocessed chunks/tasks.

## 9. Concurrency Rules
- Only one active planning/review cycle per `session_id`.
- Ingestion may process chunks in parallel but must commit state with atomic per-file updates.
- Coordinator serializes stage transitions to avoid conflicting writes.

## 10. Retention and Cleanup
- Session remains available until user ends session or configured expiration.
- On expiration, delete stored files and outputs, then remove session record.
- Cleanup action must be logged as final session event.

## 11. Definition of Done for Step 3
Step 3 is complete when:
- The session state schema is documented with concrete keys and data types.
- It explicitly supports one-time file upload reuse within a session.
- It defines lifecycle status transitions and stage guards.
- It maps agent responsibilities to state read/write ownership.
- It defines resume/idempotency behavior for large document processing.
