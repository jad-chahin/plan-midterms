# Demo Flow (ADK UI/CLI)

This is the actual user flow. No special prompt is required.

## 1) Launch ADK UI
```powershell
cd exam_study_planner
adk web
```

## 2) Upload PDFs (once per session)
- Upload each course PDF (textbook, syllabus, topic list).

## 3) Start the chat
Type something minimal like:
```text
Hi, I uploaded my PDFs. Please build my study plan.
```

## 4) Provide course mapping + dates when asked
The coordinator will ask for a mapping like:
```text
File: biology_textbook.pdf -> Course: BIO 201 -> Midterm: 2026-02-24
File: calc_topics.pdf -> Course: MATH 221 -> Midterm: 2026-02-27
File: chem_syllabus.pdf -> Course: CHEM 110 -> Midterm: 2026-02-20
```

## 5) Expected visible collaboration
- Coordinator explicitly delegates to each agent by name.
- Each agent reports its contribution.
- Coordinator summarizes and exports the plan + collaboration trace.
