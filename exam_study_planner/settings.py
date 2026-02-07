from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _load_env() -> None:
    """Load .env from repo root first, then package-local fallback."""
    package_dir = Path(__file__).resolve().parent
    repo_root = package_dir.parent
    load_dotenv(repo_root / ".env", override=False)
    load_dotenv(package_dir / ".env", override=False)


@dataclass(frozen=True)
class Settings:
    model: str
    google_api_key: str
    use_vertex_ai: str
    artifacts_dir: Path
    max_chunk_pages: int
    max_chunk_chars: int
    max_gemini_retries: int
    retry_base_seconds: float


def get_settings() -> Settings:
    _load_env()
    package_dir = Path(__file__).resolve().parent
    repo_root = package_dir.parent
    return Settings(
        model=os.getenv("GOOGLE_GEMINI_MODEL", "gemini-2.5-flash"),
        google_api_key=os.getenv("GOOGLE_API_KEY", ""),
        use_vertex_ai=os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "0"),
        artifacts_dir=Path(
            os.getenv("EXAM_STUDY_PLANNER_ARTIFACTS_DIR", str(repo_root / "artifacts"))
        ),
        max_chunk_pages=int(os.getenv("INGESTION_MAX_CHUNK_PAGES", "20")),
        max_chunk_chars=int(os.getenv("INGESTION_MAX_CHUNK_CHARS", "18000")),
        max_gemini_retries=int(os.getenv("INGESTION_MAX_GEMINI_RETRIES", "5")),
        retry_base_seconds=float(os.getenv("INGESTION_RETRY_BASE_SECONDS", "1.2")),
    )
