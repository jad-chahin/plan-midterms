# plan-my-midterms
A multi-agent system that generates a day-by-day study plan based on the topics to be covered for a student's midterms.

## Scaffold
This repo now contains a minimal Google ADK scaffold that:
- Defines three collaborating agents.
- Uses Gemini models via `.env`.
- Provides tool stubs for PDF ingestion, workload estimation, and plan export.

## Structure
- `exam_study_planner/` ADK agent config (root + sub-agents)
- `study_planner/` Python tools package
- `outputs/` Generated CSV/Markdown exports (ignored in git)

## Setup
1. Create a virtual environment and install requirements:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
2. Create `exam_study_planner/.env` using `.env.example` as a template.
   - Add your `GOOGLE_API_KEY` for Gemini.

## Run (ADK UI or CLI)
From the agent directory:
```powershell
cd exam_study_planner
adk web
```
Or:
```powershell
adk run
```

## Demo Flow
Follow the scripted prompt to make agent collaboration obvious:
- `exam_study_planner/demo_flow.md`

## Session State
- Uploaded PDFs are cached per session in memory.
- Re-ingesting the same file returns the cached summary.
- State is stored in `context.state` using `app.*` keys.

## Output Schema
The plan is validated before export and must include:
- `date`
- `course`
- `topic`
- `estimated_time`
- `notes`

## Gemini Usage
- PDF summarization and topic extraction use Gemini when `GOOGLE_API_KEY` is set.
- Topic time estimation uses Gemini and falls back to a heuristic if unavailable.
