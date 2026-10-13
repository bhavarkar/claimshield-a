"""Runtime configuration. Every Google Cloud service sits behind its own flag so the whole
pipeline runs locally with fallbacks until credentials are available."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _flag(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    project: str
    location: str
    use_docai: bool
    docai_location: str
    docai_processor_id: str
    use_bigquery: bool
    bq_dataset: str
    use_vertex_search: bool
    vertex_search_location: str
    vertex_search_datastore: str
    use_gemini: bool
    gemini_model: str
    use_gcs: bool
    gcs_bucket: str
    use_adk: bool
    data_dir: Path
    work_dir: Path
    outlier_ratio: float

    @property
    def mode_summary(self) -> dict[str, str]:
        return {
            "parsing": "Document AI" if self.use_docai else "local pdfplumber",
            "warehouse": "BigQuery" if self.use_bigquery else "local SQLite",
            "retrieval": "Vertex AI Search" if self.use_vertex_search else "local keyword retrieval",
            "reasoning": f"Gemini ({self.gemini_model})" if self.use_gemini else "deterministic templates",
            "storage": "Cloud Storage" if self.use_gcs else "local filesystem",
            "orchestration": "ADK" if self.use_adk else "plain Python runner",
        }


def load_settings() -> Settings:
    _load_dotenv(PROJECT_ROOT / ".env")
    return Settings(
        project=os.getenv("GOOGLE_CLOUD_PROJECT", ""),
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
        use_docai=_flag("CLAIMSHIELD_USE_DOCAI"),
        docai_location=os.getenv("DOCAI_LOCATION", "us"),
        docai_processor_id=os.getenv("DOCAI_PROCESSOR_ID", ""),
        use_bigquery=_flag("CLAIMSHIELD_USE_BIGQUERY"),
        bq_dataset=os.getenv("BQ_DATASET", "claimshield"),
        use_vertex_search=_flag("CLAIMSHIELD_USE_VERTEX_SEARCH"),
        vertex_search_location=os.getenv("VERTEX_SEARCH_LOCATION", "global"),
        vertex_search_datastore=os.getenv("VERTEX_SEARCH_DATASTORE_ID", ""),
        use_gemini=_flag("CLAIMSHIELD_USE_GEMINI"),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        use_gcs=_flag("CLAIMSHIELD_USE_GCS"),
        gcs_bucket=os.getenv("GCS_BUCKET", ""),
        use_adk=os.getenv("CLAIMSHIELD_USE_ADK", "true").strip().lower() in {"1", "true", "yes", "on"},
        data_dir=Path(os.getenv("CLAIMSHIELD_DATA_DIR", PROJECT_ROOT / "data")),
        work_dir=Path(os.getenv("CLAIMSHIELD_WORK_DIR", PROJECT_ROOT / "var")),
        outlier_ratio=float(os.getenv("CLAIMSHIELD_OUTLIER_RATIO", "1.3")),
    )
