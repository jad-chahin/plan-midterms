# Demo Flow (ADK UI/CLI)

Use this script to make agent collaboration obvious during a run.

## 1) Launch ADK UI
```powershell
cd exam_study_planner
adk web
```

## 2) Upload PDFs (once per session)
- Upload each course PDF (textbook, syllabus, topic list).

## 3) Paste this prompt in the UI
```text
You are the coordinator. Make collaboration obvious.
Log collaboration events using event_type values: handoff, start, end, export.
Record each handoff and when each agent completes its work.
Use the document intake agent to list and ingest all uploaded PDFs.
Then ask the workload estimator agent to estimate time per topic for each course.
Finally ask the schedule synthesis agent to build a day-by-day plan from today
through my last midterm date and export Markdown.

At the end, export the collaboration visualization.
Record the export event.

Midterm dates:
- Course A: 2026-02-20
- Course B: 2026-02-24
- Course C: 2026-02-27

Constraints:
- 2 hours per day on weekdays, 4 hours on weekends.
- Leave Sundays as light review only.
```

## 4) Expected visible collaboration
- Coordinator explicitly delegates to each agent by name.
- Each agent reports its contribution.
- Coordinator summarizes and exports the plan.
