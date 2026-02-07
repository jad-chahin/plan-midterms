# Exam Study Planner - User Input Flow

## 1. Purpose
Define a simple, unambiguous way for users to provide:
- courses,
- midterm dates,
- uploaded PDFs,
- and file-to-course mappings.

This document is the source-of-truth for step 4.

## 2. UX Principles
- Minimal steps, no unnecessary fields.
- Users upload each PDF once per session.
- Clear validation errors before planning starts.
- Same input model works in both ADK UI and ADK CLI.

## 3. Required Inputs
1. Course list (name per course).
2. Midterm date per course (`YYYY-MM-DD`).
3. PDF uploads (textbooks, syllabi, topic lists).
4. File-to-course mapping for each uploaded file:
- one course, or
- shared across multiple courses.

Optional:
- Daily study cap in minutes.
- Preferred rest day.

## 4. UI Flow (ADK Built-in UI)
### Step A: Session Setup
Fields:
- `timezone` (default from browser/session).
- `daily_study_cap_minutes` (optional, integer).
- `preferred_rest_day` (optional).

Action:
- `Continue to Courses`

### Step B: Courses and Midterms
Dynamic table rows:
- `course_name` (text, required)
- `midterm_date` (date, required)

Actions:
- `Add Course`
- `Continue to Documents`

Validation:
- At least 1 course.
- No empty course names.
- Valid date format.
- Midterm date must be today or future date.

### Step C: Upload PDFs
Actions:
- `Upload PDF` (multiple allowed)
- Show uploaded file list with size and status.

Validation:
- Only `.pdf` accepted.
- Duplicate file (same checksum+size) is de-duplicated and reused.

### Step D: Map Files to Courses
For each file:
- Select one or more courses (multi-select).
- Toggle `Shared` when file applies broadly.

Validation:
- Every file must be mapped to at least one course or `Shared`.
- Every course must have at least one mapped file or direct topic input.

### Step E: Review and Start Planning
Review page shows:
- Course/date table.
- Uploaded file inventory.
- Mapping summary.

Action:
- `Start Planning`

System behavior:
- Persist finalized inputs to session state.
- Trigger `CoordinatorAgent` orchestration pipeline.

## 5. CLI Flow (ADK Built-in CLI)
Single command accepts structured JSON input and file paths.

Example:
```bash
adk run exam-study-planner \
  --input-file inputs/session_input.json \
  --files "C:/docs/calc_textbook.pdf" "C:/docs/bio_syllabus.pdf"
```

`inputs/session_input.json` schema:
```json
{
  "timezone": "America/Los_Angeles",
  "daily_study_cap_minutes": 240,
  "preferred_rest_day": "Sunday",
  "courses": [
    {
      "course_name": "Calculus II",
      "midterm_date": "2026-02-21"
    },
    {
      "course_name": "Biology",
      "midterm_date": "2026-02-24"
    }
  ],
  "file_course_mapping": [
    {
      "filename": "calc_textbook.pdf",
      "course_names": ["Calculus II"],
      "shared": false
    },
    {
      "filename": "general_study_skills.pdf",
      "course_names": ["Calculus II", "Biology"],
      "shared": true
    }
  ]
}
```

## 6. Canonical Input Payload (Internal)
After UI/CLI normalization, coordinator receives:
```json
{
  "session_id": "string",
  "timezone": "string",
  "daily_study_cap_minutes": 240,
  "preferred_rest_day": "Sunday",
  "courses": [
    {
      "course_id": "string",
      "course_name": "string",
      "midterm_date": "YYYY-MM-DD"
    }
  ],
  "files": [
    {
      "file_id": "string",
      "filename": "string",
      "sha256": "string",
      "size_bytes": 1234,
      "course_ids": ["string"],
      "is_shared": false
    }
  ]
}
```

## 7. Validation Error Messages (Examples)
- `Course name is required.`
- `Midterm date for Biology must be on or after 2026-02-07.`
- `Only PDF files are supported: notes.docx was rejected.`
- `File calc_textbook.pdf must be mapped to at least one course or marked shared.`
- `Course World History has no mapped files or direct topics.`

## 8. Definition of Done for Step 4
Step 4 is complete when:
- The user flow is documented end-to-end for ADK UI and ADK CLI.
- Required fields and validation rules are explicit.
- File-to-course mapping format is fully specified.
- A canonical normalized input payload contract exists for coordinator handoff.
