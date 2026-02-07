# Exam Study Planner - Step 9 Schedule Planning Agent

## Implemented
- Added a dedicated planning module that converts topic workload estimates into
  day-by-day study rows from `today` through `last_midterm_date`.
- Added persisted `planning_state` in session `state.json` with:
  - `plan_version`
  - `last_midterm_date`
  - `plan_rows[]`
  - `warnings[]`
- Added ADK tools for planning workflow:
  - `build_session_study_plan`
  - `read_planning_state`
- Wired `PlanningReviewerAgent` to use planning tools.

## Scheduling Behavior
- Reads inputs from:
  - `user_inputs.courses`
  - `estimation_state.topic_estimates`
- Enforces course-specific midterm deadlines.
- Allocates study in minute blocks (`min_block_minutes` to `max_block_minutes`)
  under a daily cap (`daily_study_cap_minutes`).
- Generates at least one row per day in range:
  - if no topic work is schedulable for a day, inserts `Buffer/Review` row.
- Produces warnings if some topic minutes cannot be fully scheduled before
  their respective midterms.

## Plan Row Schema
- `date`
- `course`
- `topic`
- `task_description`
- `estimated_minutes`
- `priority`
- `source_files`
- `status`

## Files Updated
- `exam_study_planner/planning.py` (new)
- `exam_study_planner/tools.py`
- `exam_study_planner/agent.py`

## Step 9 Definition of Done Check
- Schedule planning agent exists and is callable via ADK tools: implemented.
- Day-by-day allocations are generated through the latest midterm date: implemented.
- Output shape matches required planning row structure: implemented.
