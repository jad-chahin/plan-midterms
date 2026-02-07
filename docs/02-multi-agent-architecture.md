# Exam Study Planner - Multi-Agent Architecture

## 1. Purpose
Define the minimum multi-agent design (3+ agents) for ADK-based orchestration, including:
- clear responsibilities per agent,
- explicit handoff contracts between agents,
- and visible collaboration events in ADK UI.

This document is the source-of-truth for step 2.

## 2. Agent Team
The system uses 4 agents to satisfy the "at least 3" requirement and improve reliability.

1. `CoordinatorAgent`
- Owns end-to-end workflow and session-level orchestration.
- Validates required inputs are present before downstream execution.
- Dispatches work to specialist agents and aggregates final outputs.

2. `IngestionAgent`
- Handles uploaded PDF inventory, chunking strategy, and extraction workflow.
- Produces normalized topic evidence per course from textbooks/syllabi/topic docs.
- Records extraction progress so processing can resume if interrupted.

3. `EstimationAgent`
- Converts extracted topics/evidence into workload estimates (`estimated_minutes`, difficulty, confidence).
- Flags uncertain estimates that require reviewer checks.

4. `PlanningReviewerAgent`
- Generates day-by-day schedule from today through last midterm date.
- Validates feasibility (coverage, date constraints, per-day load balance).
- Performs revision loop if constraints are violated, then approves final plan.

## 3. Orchestration Sequence
1. `CoordinatorAgent` receives user inputs and checks completeness.
2. `CoordinatorAgent` -> `IngestionAgent` with file/course mapping.
3. `IngestionAgent` returns normalized course-topic evidence.
4. `CoordinatorAgent` -> `EstimationAgent` with topic evidence.
5. `EstimationAgent` returns workload estimates and confidence signals.
6. `CoordinatorAgent` -> `PlanningReviewerAgent` with estimates and date constraints.
7. `PlanningReviewerAgent` returns:
- either `needs_revision` with reasons and requested changes,
- or `capacity_limited_plan` when constraints are valid but full coverage is mathematically impossible,
- or `approved_plan` with final row-level schedule.
8. If revision required, `CoordinatorAgent` may re-invoke `EstimationAgent` and/or `PlanningReviewerAgent`.
9. On approval, `CoordinatorAgent` emits final canonical plan payload for CSV/Markdown generation.

## 4. Handoff Contracts
All handoffs are JSON-serializable ADK payloads.

### 4.1 Coordinator -> Ingestion
```json
{
  "session_id": "string",
  "courses": [
    {
      "course_id": "string",
      "course_name": "string",
      "midterm_date": "YYYY-MM-DD",
      "file_ids": ["string"]
    }
  ],
  "shared_file_ids": ["string"],
  "ingestion_config": {
    "chunking_mode": "page_window",
    "max_pages_per_chunk": 20
  }
}
```

### 4.2 Ingestion -> Coordinator
```json
{
  "session_id": "string",
  "course_topic_evidence": [
    {
      "course_id": "string",
      "topic": "string",
      "evidence_summary": "string",
      "source_files": ["string"],
      "source_chunks": ["string"]
    }
  ],
  "ingestion_status": "complete|partial|failed",
  "warnings": ["string"]
}
```

### 4.3 Coordinator -> Estimation
```json
{
  "session_id": "string",
  "course_topic_evidence": [
    {
      "course_id": "string",
      "topic": "string",
      "evidence_summary": "string",
      "source_files": ["string"]
    }
  ],
  "constraints": {
    "start_date": "YYYY-MM-DD",
    "last_midterm_date": "YYYY-MM-DD"
  }
}
```

### 4.4 Estimation -> Coordinator
```json
{
  "session_id": "string",
  "topic_estimates": [
    {
      "course_id": "string",
      "topic": "string",
      "estimated_minutes": 90,
      "priority": "high|medium|low",
      "confidence": 0.0
    }
  ],
  "uncertainty_flags": ["string"]
}
```

### 4.5 Coordinator -> PlanningReviewer
```json
{
  "session_id": "string",
  "courses": [
    {
      "course_id": "string",
      "course_name": "string",
      "midterm_date": "YYYY-MM-DD"
    }
  ],
  "topic_estimates": [
    {
      "course_id": "string",
      "topic": "string",
      "estimated_minutes": 90,
      "priority": "high|medium|low"
    }
  ],
  "planning_rules": {
    "include_every_date": true,
    "end_at_last_midterm": true
  }
}
```

### 4.6 PlanningReviewer -> Coordinator
```json
{
  "session_id": "string",
  "result_type": "needs_revision|capacity_limited_plan|approved_plan",
  "revision_reasons": ["string"],
  "plan_rows": [
    {
      "date": "YYYY-MM-DD",
      "course": "string",
      "topic": "string",
      "task_description": "string",
      "estimated_minutes": 90,
      "priority": "high|medium|low",
      "source_files": ["string"],
      "status": "planned"
    }
  ],
  "validation_report": {
    "coverage_ok": true,
    "date_range_ok": true,
    "load_balance_ok": true
  }
}
```

## 5. ADK UI Collaboration Visibility
The following must be visible in ADK UI timeline/log stream:
- Agent invocation start/finish for each agent.
- Handoff summary entries with payload metadata (counts, IDs, warnings).
- Planning review verdict (`needs_revision`, `capacity_limited_plan`, or `approved_plan`) and reasons.
- Revision loop steps when plan is rejected.
- Final coordinator approval event before export.

Minimum required UI event fields:
- `timestamp`
- `session_id`
- `agent_name`
- `event_type` (`invoke`, `handoff`, `review`, `revision`, `complete`, `error`)
- `summary`
- `artifact_refs` (optional IDs to generated payloads/files)

## 6. Error and Recovery Model
- If ingestion is partial, `CoordinatorAgent` proceeds only for courses with usable evidence and records missing coverage warnings.
- If estimation has low confidence, planner still runs but marks rows for review.
- If planner validation fails for non-capacity issues, `PlanningReviewerAgent` must return `needs_revision` and explicit reasons.
- Hard failure in any agent results in a coordinator error event with step context and retry status.

## 7. Non-Goals for Step 2
- No implementation code in this step.
- No final persistence schema definition (covered in step 3).
- No UI form implementation (covered in step 4).

## 8. Definition of Done for Step 2
Step 2 is complete when:
- At least 3 distinct agents are defined with non-overlapping core responsibilities.
- A concrete orchestration sequence is documented.
- Handoff contracts are documented with required fields.
- ADK UI visibility requirements for collaboration are explicitly defined.
