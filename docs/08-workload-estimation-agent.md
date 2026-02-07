# Exam Study Planner - Step 8 Workload Estimation Agent

## Implemented
- Added a dedicated estimation module that converts ingestion evidence into
  structured topic-level workload estimates.
- Added persisted `estimation_state` in session `state.json` with:
  - `topic_estimates[]`
  - `uncertainty_flags[]`
- Added ADK tools for estimation workflow:
  - `estimate_session_workload`
  - `read_estimation_state`
- Wired `EstimationAgent` to use these tools directly.

## Estimate Output Schema
Each estimate row includes:
- `course_id`
- `topic`
- `estimated_minutes`
- `priority` (`high|medium|low`)
- `confidence` (`0.0` to `1.0`)
- `rationale`
- `source_files`

## Behavior
- Reads normalized input from `ingestion_state.course_topic_evidence`.
- Uses Gemini (JSON-only response contract) when API key is present.
- Falls back to deterministic heuristics on missing key or model failures.
- Applies retry/backoff for transient Gemini failures.
- Flags low-confidence estimates (`confidence < 0.6`) into `uncertainty_flags`.

## Files Updated
- `exam_study_planner/estimation.py` (new)
- `exam_study_planner/tools.py`
- `exam_study_planner/agent.py`

## Step 8 Definition of Done Check
- Workload estimation agent exists and is callable via ADK tools: implemented.
- Structured estimate output is persisted and reusable: implemented.
- Confidence and uncertainty signaling exists: implemented.
