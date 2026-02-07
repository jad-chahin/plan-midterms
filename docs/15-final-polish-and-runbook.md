# Exam Study Planner - Step 15 Final Polish and Runbook

## Scope Completed
- Finalized repository runbook for setup, execution, workflow, and recovery.
- Consolidated operational guidance in `README.md`.
- Added troubleshooting and verification commands for ADK CLI/UI usage.

## Operator Runbook

### 1. Environment Setup
1. Install Python 3.12+.
2. Install dependencies:
```bash
venv/Scripts/python.exe -m pip install -r requirements.txt
```
3. Configure `.env`:
```env
GOOGLE_GENAI_USE_VERTEXAI=0
GOOGLE_API_KEY=YOUR_GEMINI_API_KEY
GOOGLE_GEMINI_MODEL=gemini-2.5-flash
```

### 2. Launch ADK
Web UI:
```bash
venv/Scripts/adk.exe web .
```
Open: `http://127.0.0.1:8000`

CLI:
```bash
venv/Scripts/adk.exe run exam_study_planner
```

### 3. Session Workflow
1. Register courses with `course_id`, `course_name`, `midterm_date`.
2. Upload PDFs in ADK Web UI chat.
3. Call `list_uploaded_session_files`.
4. Call `register_uploaded_session_files` to register uploaded artifacts.
5. Map each file to course(s) or mark shared.
6. Run chunked ingestion.
7. Run workload estimation.
8. Build schedule.
9. Review/validate schedule.
10. Export CSV + Markdown artifacts.
11. Read collaboration trace and artifact paths.

### 3.1 One-Shot Simplified Workflow
If you want one command instead of many tool calls:
```text
Call run_simple_study_planner with:
{
  "session_id": "my_midterms_01",
  "course_names": ["Business Dynamics", "Biostatistics", "Quantum Mechanics"],
  "midterm_dates": ["2026-02-21", "2026-02-24", "2026-02-26"],
  "daily_study_cap_minutes": 240
}
```
Behavior:
- reads uploaded PDFs from the current ADK Web UI session
- auto-registers files
- auto-maps files to courses by filename keywords (unmatched files become shared)
- runs ingestion, estimation, planning, review, export

### 4. Verification Commands
Run E2E tests:
```bash
venv/Scripts/python.exe -m unittest tests/test_e2e_pipeline.py -v
```
Basic import check:
```bash
venv/Scripts/python.exe -c "from exam_study_planner import root_agent; print(root_agent.name)"
```

### 5. Troubleshooting
- Missing `GOOGLE_API_KEY`:
  - pipeline still runs with deterministic fallback; semantic quality is lower.
- Stage returns `status=failed`:
  - inspect `stage`, `error`, `retryable`.
  - read session trace via `read_session_collaboration_trace`.
- Ingestion warnings/partial:
  - rerun ingestion with `force_reprocess=True`.
- Planning/export missing prerequisites:
  - ensure earlier stages completed and wrote state.
- Upload registration issues:
  - call `list_uploaded_session_files` to verify the file names in session.
  - pass exact artifact filenames to `register_uploaded_session_files`.
- Stale/bad session:
  - remove `artifacts/sessions/<session_id>/` and rerun.

### 6. Output Locations
- Session state: `artifacts/sessions/<session_id>/state.json`
- Final CSV: `artifacts/sessions/<session_id>/outputs/study_plan.csv`
- Final Markdown: `artifacts/sessions/<session_id>/outputs/study_plan.md`

## Step 15 Definition of Done Check
- README includes setup and run commands for ADK CLI/UI: complete.
- README includes expected end-user workflow: complete.
- Troubleshooting guidance is documented: complete.
- Dedicated runbook document exists for operators: complete.
