#!/usr/bin/env bash
# One-time Google Cloud setup for ClaimShield AI. Idempotent: safe to re-run.
# Needs: gcloud authenticated (gcloud auth login && gcloud auth application-default login).
# Prints the .env values to use at the end.
set -euo pipefail

PROJECT="${GOOGLE_CLOUD_PROJECT:?set GOOGLE_CLOUD_PROJECT}"
REGION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
DOCAI_LOCATION="${DOCAI_LOCATION:-us}"
BUCKET="${GCS_BUCKET:-${PROJECT}-claimshield}"
DATASET="${BQ_DATASET:-claimshield}"
DATASTORE="${VERTEX_SEARCH_DATASTORE_ID:-claimshield-policies}"
SA="claimshield-run@${PROJECT}.iam.gserviceaccount.com"

gcloud config set project "$PROJECT" >/dev/null

echo "==> Enabling APIs"
gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  documentai.googleapis.com bigquery.googleapis.com discoveryengine.googleapis.com \
  aiplatform.googleapis.com storage.googleapis.com logging.googleapis.com

echo "==> Cloud Storage bucket gs://$BUCKET"
gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://$BUCKET" --location="$REGION" --uniform-bucket-level-access

echo "==> BigQuery dataset $DATASET"
bq --location=US show "$PROJECT:$DATASET" >/dev/null 2>&1 || bq --location=US mk --dataset "$PROJECT:$DATASET"

echo "==> Service account $SA"
gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 || \
  gcloud iam service-accounts create claimshield-run --display-name="ClaimShield Cloud Run"
for role in roles/documentai.apiUser roles/bigquery.dataEditor roles/bigquery.jobUser \
            roles/discoveryengine.viewer roles/aiplatform.user roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA" --role="$role" --condition=None >/dev/null
done
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$SA" --role=roles/storage.objectAdmin >/dev/null

TOKEN="$(gcloud auth print-access-token)"

echo "==> Document AI Form Parser processor"
PROCESSOR_ID="$(curl -s -H "Authorization: Bearer $TOKEN" \
  "https://${DOCAI_LOCATION}-documentai.googleapis.com/v1/projects/${PROJECT}/locations/${DOCAI_LOCATION}/processors" \
  | python3 -c "import sys,json; ps=[p for p in json.load(sys.stdin).get('processors',[]) if p.get('displayName')=='claimshield-form-parser']; print(ps[0]['name'].split('/')[-1] if ps else '')")"
if [ -z "$PROCESSOR_ID" ]; then
  PROCESSOR_ID="$(curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d '{"type":"FORM_PARSER_PROCESSOR","displayName":"claimshield-form-parser"}' \
    "https://${DOCAI_LOCATION}-documentai.googleapis.com/v1/projects/${PROJECT}/locations/${DOCAI_LOCATION}/processors" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['name'].split('/')[-1])")"
fi

echo "==> Vertex AI Search data store $DATASTORE (layout-based chunking)"
curl -s -o /dev/null -w "   create data store: HTTP %{http_code} (409 = already exists)\n" -X POST \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -H "X-Goog-User-Project: $PROJECT" \
  "https://discoveryengine.googleapis.com/v1/projects/${PROJECT}/locations/global/collections/default_collection/dataStores?dataStoreId=${DATASTORE}" \
  -d '{
    "displayName": "ClaimShield policies",
    "industryVertical": "GENERIC",
    "solutionTypes": ["SOLUTION_TYPE_SEARCH"],
    "contentConfig": "CONTENT_REQUIRED",
    "documentProcessingConfig": {
      "chunkingConfig": {"layoutBasedChunkingConfig": {"chunkSize": 300, "includeAncestorHeadings": true}},
      "defaultParsingConfig": {"layoutParsingConfig": {}}
    }
  }'

cat <<ENV

Done. Put these in .env (and they are passed to Cloud Run by scripts/deploy_cloud_run.sh):

GOOGLE_CLOUD_PROJECT=$PROJECT
GOOGLE_CLOUD_LOCATION=$REGION
CLAIMSHIELD_USE_DOCAI=true
DOCAI_LOCATION=$DOCAI_LOCATION
DOCAI_PROCESSOR_ID=$PROCESSOR_ID
CLAIMSHIELD_USE_BIGQUERY=true
BQ_DATASET=$DATASET
CLAIMSHIELD_USE_VERTEX_SEARCH=true
VERTEX_SEARCH_DATASTORE_ID=$DATASTORE
CLAIMSHIELD_USE_GEMINI=true
CLAIMSHIELD_USE_GCS=true
GCS_BUCKET=$BUCKET

Next: make bq-load && make index-policies && make deploy
ENV
