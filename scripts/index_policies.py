"""Upload the sample policies to Cloud Storage and import them into the Vertex AI Search data
store. Indexing runs asynchronously and usually takes a few minutes; until it finishes, the
policy agent falls back to local retrieval (the trace says so).

    python scripts/index_policies.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from google.cloud import discoveryengine_v1 as de  # noqa: E402
from google.cloud import storage  # noqa: E402

from claimshield.config import load_settings  # noqa: E402


def main() -> None:
    s = load_settings()
    if not (s.project and s.gcs_bucket and s.vertex_search_datastore):
        sys.exit("Set GOOGLE_CLOUD_PROJECT, GCS_BUCKET and VERTEX_SEARCH_DATASTORE_ID.")
    bucket = storage.Client(project=s.project).bucket(s.gcs_bucket)
    uris = []
    for pdf in sorted((ROOT / "data" / "samples" / "policies").glob("*.pdf")):
        blob = bucket.blob(f"policies/{pdf.name}")
        blob.upload_from_filename(str(pdf), content_type="application/pdf")
        uris.append(f"gs://{s.gcs_bucket}/policies/{pdf.name}")
        print("uploaded", uris[-1])

    client = de.DocumentServiceClient()
    parent = (f"projects/{s.project}/locations/{s.vertex_search_location}/collections/default_collection/"
              f"dataStores/{s.vertex_search_datastore}/branches/default_branch")
    op = client.import_documents(request=de.ImportDocumentsRequest(
        parent=parent,
        gcs_source=de.GcsSource(input_uris=uris, data_schema="content"),
        reconciliation_mode=de.ImportDocumentsRequest.ReconciliationMode.INCREMENTAL,
    ))
    print("import started:", op.operation.name)
    result = op.result(timeout=900)
    print("import finished; errors:", list(result.error_samples) or "none")


if __name__ == "__main__":
    main()
