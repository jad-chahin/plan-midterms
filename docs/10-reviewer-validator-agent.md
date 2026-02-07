# Exam Study Planner - Step 10 Reviewer/Validator Agent

## Implemented
- Added dedicated review/validation module for plan feasibility checks.
- Added review tool callable by `PlanningReviewerAgent`:
  - `review_session_plan(...)`
- Added persisted review verdict under `planning_state.review`:
  - `result_type` (`approved_plan|capacity_limited_plan|needs_revision`)
  - `revision_reasons[]`
  - `validation_report`
  - `revision_rounds`
  - `effective_daily_study_cap_minutes`

## Validation Checks
- `coverage_ok`: every estimated topic appears in plan rows.
- `date_range_ok`: all dates from today to last midterm are present.
- `load_balance_ok`: per-day minutes do not exceed daily cap.
- `deadline_ok`: no course tasks are scheduled after that course midterm date.

## Revision Loop
- If validation fails and auto-revision enabled:
  - planner is re-run with adjusted parameters (currently increases cap when
    load issues are detected),
  - validation is re-run,
  - final verdict is recorded as `approved_plan`, `capacity_limited_plan`, or `needs_revision`.

## Files Updated
- `exam_study_planner/review.py` (new)
- `exam_study_planner/tools.py`
- `exam_study_planner/agent.py`

## Step 10 Definition of Done Check
- Reviewer/validator agent function exists and runs after planning: implemented.
- Feasibility checks are explicit and persisted: implemented.
- Needs-revision pathway is explicit with reasons: implemented.
