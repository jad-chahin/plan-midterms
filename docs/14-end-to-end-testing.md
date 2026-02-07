# Exam Study Planner - Step 14 End-to-End Testing

## Implemented
- Added end-to-end automated test suite:
  - `tests/test_e2e_pipeline.py`
- Test coverage includes realistic multi-course scenarios with large synthetic
  PDF inputs and varied midterm date windows.

## Covered Scenarios
1. Three-course full pipeline with large docs and shared file:
- register courses
- upload/map multiple PDFs
- chunked ingestion
- estimation
- day-by-day planning
- review/validation
- CSV/Markdown export
- collaboration trace schema validation

2. Different midterm date ranges:
- validates planning start and end date behavior
- verifies exported markdown sections and successful artifact generation

## Validation Targets
- pipeline completes end-to-end without manual intervention
- output artifacts exist
- collaboration events exist with required fields
- plan date window covers today through latest midterm

## Notes
- Tests use deterministic fallback mode (`GOOGLE_API_KEY=''`) so they run
  reliably in local CI-like environments without external API dependency.
- This verifies orchestration and resilience behavior; quality of model-derived
  semantic extraction under live Gemini is validated in runtime environments.
