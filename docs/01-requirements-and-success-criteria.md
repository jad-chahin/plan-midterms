# Exam Study Planner - Requirements and Success Criteria

## 1. Project Objective
Build a multi-agent AI system (using Google ADK and Gemini) that generates a day-by-day study plan for a student with 3 midterms in the next 2-3 weeks.

The plan must cover every date from the user's current date through the date of their last midterm and include course-specific study tasks.

## 2. Mandatory Constraints
- Use Google Agent Development Kit (ADK) throughout the workflow.
- Use Gemini API for model calls (API key provided via `.env`).
- Use ADK built-in CLI and built-in UI.
- Define at least 3 distinct collaborating agents with clear responsibilities.
- Collaboration among agents must be visible in ADK UI.
- User can upload large PDF documents (textbooks, syllabi, midterm topics).
- Large PDF handling must stay within token limits and avoid rate limiting (chunking + multiple calls as needed).
- State must persist for one user session so files are uploaded only once per session.
- Final output must be generated in both CSV and Markdown with predictable schema.

## 3. User Inputs
The system must collect:
- Courses (at least 3 supported; no hard cap required).
- Midterm date per course.
- Mapping of uploaded files to courses.
- Optional topic priorities or constraints if provided by user.

### 3.1 Accepted File Types
- PDF only for document uploads in scope for this project.

### 3.2 Input Validation Rules
- Every course must have a valid midterm date.
- Every uploaded file must be mapped to one course or marked as shared.
- At least one source file or direct topic input must exist per course.

## 4. System Capabilities
### 4.1 Multi-Agent Orchestration
Minimum required agent roles:
- `IngestionAgent`: handles file intake, chunking, extraction coordination.
- `EstimationAgent`: estimates study effort by topic.
- `PlanningAgent`: builds day-by-day schedule through last midterm.
- `ReviewAgent` (recommended): validates feasibility and coverage before final export.

### 4.2 Large Document Processing
- Process large PDFs in chunks.
- Maintain per-file progress and partial extraction state in session.
- Retry/backoff on rate-limit or transient failures.
- Aggregate chunk outputs into normalized course/topic summaries.

### 4.3 Session State Management
Session state must include:
- Uploaded file metadata and storage references.
- Course-to-file mappings.
- Extracted topics and estimates.
- Generated plan drafts and final plan artifacts.

State must be reusable across multiple agent invocations in the same session.

### 4.4 Output Generation
Produce both:
- `study_plan.md`
- `study_plan.csv`

Outputs must represent the same schedule content.

## 5. Output Format Contract
### 5.1 CSV Columns (required order)
1. `date`
2. `course`
3. `topic`
4. `task_description`
5. `estimated_minutes`
6. `priority`
7. `source_files`
8. `status`

### 5.2 Markdown Structure (required sections)
1. `# Exam Study Plan`
2. `## Student Inputs`
3. `## Planning Assumptions`
4. `## Day-by-Day Plan`
5. `## Coverage Check by Course`

## 6. Non-Functional Requirements
- Deterministic structured output shape (stable keys/columns/sections).
- Basic fault tolerance for failed chunk calls and rate limits.
- Reasonable latency for medium/large documents through staged processing.
- Clear auditability in UI showing which agent produced which intermediate result.

## 7. Definition of Done for Step 1
Step 1 is complete when:
- This document exists in the repo and is the source-of-truth for requirements.
- It includes objective, inputs, constraints, output contract, and success criteria.
- It defines the minimum agent count and responsibilities.
- It explicitly specifies CSV/Markdown output schema.

## 8. Example Output Snippets
### 8.1 CSV Example
```csv
date,course,topic,task_description,estimated_minutes,priority,source_files,status
2026-02-08,Calculus II,Integration by Parts,Read worked examples and solve 8 problems,90,high,calc_syllabus.pdf;calc_midterm_topics.pdf,planned
2026-02-08,Biology,Cellular Respiration,Summarize chapter and complete flashcards,60,medium,bio_textbook.pdf,planned
```

### 8.2 Markdown Example
```md
# Exam Study Plan

## Student Inputs
- Courses: Calculus II, Biology, World History
- Midterms: 2026-02-21, 2026-02-24, 2026-02-26

## Planning Assumptions
- Study window starts at current session date.
- Higher estimated-effort topics scheduled earlier.

## Day-by-Day Plan
| Date | Course | Topic | Task | Minutes |
|---|---|---|---|---|
| 2026-02-08 | Calculus II | Integration by Parts | Practice set A | 90 |

## Coverage Check by Course
- Calculus II: 100% listed topics scheduled.
```
