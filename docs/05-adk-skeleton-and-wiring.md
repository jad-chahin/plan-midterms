# Exam Study Planner - ADK Skeleton and Wiring

## Implemented for Step 5
- ADK-compatible agent package at `exam_study_planner/`.
- Root agent export in `exam_study_planner/__init__.py`.
- Base multi-agent orchestration in `exam_study_planner/agent.py`.
- Environment loading from `.env` in `exam_study_planner/settings.py`.
- Run instructions for ADK CLI/UI in `README.md`.

## Entry Points
- CLI: `adk run exam_study_planner`
- Web UI: `adk web .`

## Local Verification Performed
- Python import/compile check passed for agent modules.
- `adk run exam_study_planner` starts interactive session successfully.
- `adk web . --port 8014 --no-reload` verified listening on `127.0.0.1:8014`.

## Notes
- This is a functional skeleton with orchestration wiring.
- Full ingestion, estimation, planning logic and persistent state internals are
  implemented in subsequent steps.
