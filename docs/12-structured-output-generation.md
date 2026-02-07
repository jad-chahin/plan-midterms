# Exam Study Planner - Step 12 Structured Output Generation

## Implemented
- Added deterministic export module for final artifacts:
  - `study_plan.csv`
  - `study_plan.md`
- Added export tools:
  - `export_session_study_plan(session_id, overwrite)`
  - `read_session_output_artifacts(session_id)`
- Wired export into `PlanningReviewerAgent` workflow after review.

## Deterministic CSV Contract
CSV columns are written in fixed order:
1. `date`
2. `course`
3. `topic`
4. `task_description`
5. `estimated_minutes`
6. `priority`
7. `source_files`
8. `status`

Rows are sorted deterministically by:
- `date`, `course`, `topic`, `task_description`

## Deterministic Markdown Contract
Markdown always includes sections:
1. `# Exam Study Plan`
2. `## Student Inputs`
3. `## Planning Assumptions`
4. `## Day-by-Day Plan`
5. `## Coverage Check by Course`

## Session Artifact Persistence
Export updates session state:
- `artifacts.csv_path`
- `artifacts.markdown_path`
- lifecycle status set to `completed`

## Files Updated
- `exam_study_planner/export.py` (new)
- `exam_study_planner/tools.py`
- `exam_study_planner/agent.py`

## Step 12 Definition of Done Check
- Final output generated as both CSV and Markdown: implemented.
- Output schema/structure is stable and predictable: implemented.
- Artifact paths are persisted in session state: implemented.
