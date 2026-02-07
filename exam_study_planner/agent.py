from __future__ import annotations

from google.adk.agents import Agent, SequentialAgent

from .settings import get_settings
from .tools import (
    build_session_study_plan,
    estimate_session_workload,
    export_session_study_plan,
    read_session_collaboration_trace,
    read_session_output_artifacts,
    read_planning_state,
    review_session_plan,
    read_estimation_state,
    ingest_session_documents,
    map_session_files_to_courses,
    read_ingestion_state,
    register_session_courses,
    register_session_files,
    record_session_collaboration_event,
    run_simple_study_planner,
)

SETTINGS = get_settings()


ingestion_agent = Agent(
    model=SETTINGS.model,
    name="IngestionAgent",
    description="Extracts and normalizes course topics from PDF files.",
    instruction=(
        "You are the IngestionAgent for an exam study planner. "
        "You must use tools to register courses, register files, and map files to courses "
        "before ingestion. "
        "If the user asks for a simpler flow, prefer run_simple_study_planner. "
        "Workflow: (1) call register_session_courses, "
        "(2) call register_session_files using file paths, "
        "(3) call map_session_files_to_courses, "
        "(4) call ingest_session_documents, "
        "(5) call read_ingestion_state, "
        "(6) call read_session_collaboration_trace, then summarize course-by-course topic evidence "
        "and mapping quality. "
        "Do not claim ingestion is complete unless ingest_session_documents result says so."
    ),
    tools=[
        register_session_courses,
        run_simple_study_planner,
        register_session_files,
        map_session_files_to_courses,
        ingest_session_documents,
        read_ingestion_state,
        read_session_collaboration_trace,
        record_session_collaboration_event,
    ],
    output_key="ingestion_output",
)

estimation_agent = Agent(
    model=SETTINGS.model,
    name="EstimationAgent",
    description="Estimates study workload by topic.",
    instruction=(
        "You are the EstimationAgent. "
        "Use tools to produce structured workload estimates from ingestion output. "
        "Workflow: (1) call estimate_session_workload, (2) call read_estimation_state, "
        "(3) call read_session_collaboration_trace, "
        "then summarize total estimates and uncertainty flags. "
        "Return course/topic-level outputs with estimated_minutes, priority, and confidence."
    ),
    tools=[
        estimate_session_workload,
        read_estimation_state,
        read_session_collaboration_trace,
        record_session_collaboration_event,
    ],
    output_key="estimation_output",
)

planning_reviewer_agent = Agent(
    model=SETTINGS.model,
    name="PlanningReviewerAgent",
    description="Builds and validates a day-by-day plan through the last midterm.",
    instruction=(
        "You are the PlanningReviewerAgent. "
        "Use tools to build a day-by-day study schedule from today through the last "
        "midterm date. "
        "Workflow: (1) call build_session_study_plan, (2) call review_session_plan, "
        "(3) call export_session_study_plan, (4) call read_planning_state, "
        "(5) call read_session_output_artifacts, "
        "(6) call read_session_collaboration_trace, "
        "then summarize verdict, validation report, and "
        "revision reasons if any."
    ),
    tools=[
        build_session_study_plan,
        review_session_plan,
        export_session_study_plan,
        read_planning_state,
        read_session_output_artifacts,
        read_session_collaboration_trace,
        record_session_collaboration_event,
    ],
    output_key="planning_output",
)


root_agent = SequentialAgent(
    name="CoordinatorAgent",
    description=(
        "Orchestrates IngestionAgent, EstimationAgent, and PlanningReviewerAgent in "
        "sequence for the Exam Study Planner."
    ),
    sub_agents=[ingestion_agent, estimation_agent, planning_reviewer_agent],
)
