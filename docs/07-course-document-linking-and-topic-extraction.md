# Exam Study Planner - Step 7 Course Linking and Topic Extraction

## Implemented
- Session-level course registration with validation:
  - `course_id`
  - `course_name`
  - `midterm_date` (`YYYY-MM-DD`, today or future)
- Explicit file-to-course mapping after upload:
  - map by `file_id` or `filename`
  - support direct course mapping or `is_shared=true`
- Shared file expansion:
  - shared files are automatically applied to all registered courses.
- Topic normalization for deterministic de-duplication:
  - normalized field: `normalized_topic`
  - merge key: `(course_id, normalized_topic)`
- Course-scoped topic evidence output:
  - `course_id`
  - `topic`
  - `normalized_topic`
  - `evidence_summary`
  - `source_files`
  - `source_chunks`

## New/Updated Tools
- `register_session_courses(session_id, courses)`
- `register_session_files(session_id, files)`
- `map_session_files_to_courses(session_id, mappings)`
- `ingest_session_documents(...)`
- `read_ingestion_state(session_id)`

## Files Updated
- `exam_study_planner/ingestion.py`
- `exam_study_planner/tools.py`
- `exam_study_planner/agent.py`

## Validation Performed
Smoke test executed with synthetic text PDFs:
- registered 2 courses
- uploaded 2 files
- mapped one file to a single course and one as shared
- ingested documents
- verified extracted output contains both courses
- verified `normalized_topic` exists on all topic rows

## Step 7 Definition of Done Check
- User can specify which files correspond to which courses: implemented.
- Shared and course-specific file mapping both supported: implemented.
- Topic extraction is course-aware and normalized: implemented.
