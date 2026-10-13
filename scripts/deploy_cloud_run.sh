#!/usr/bin/env bash
# Build with Cloud Build and deploy to Cloud Run, passing the .env settings through.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a

PROJECT="${GOOGLE_CLOUD_PROJECT:?set GOOGLE_CLOUD_PROJECT}"
REGION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
SERVICE="${SERVICE:-claimshield-ai}"
SA="claimshield-run@${PROJECT}.iam.gserviceaccount.com"

ENV_VARS=""
for k in GOOGLE_CLOUD_PROJECT GOOGLE_CLOUD_LOCATION CLAIMSHIELD_USE_DOCAI DOCAI_LOCATION DOCAI_PROCESSOR_ID \
         CLAIMSHIELD_USE_BIGQUERY BQ_DATASET CLAIMSHIELD_USE_VERTEX_SEARCH VERTEX_SEARCH_LOCATION \
         VERTEX_SEARCH_DATASTORE_ID CLAIMSHIELD_USE_GEMINI GEMINI_MODEL CLAIMSHIELD_USE_GCS GCS_BUCKET \
         CLAIMSHIELD_USE_ADK CLAIMSHIELD_OUTLIER_RATIO CLAIMSHIELD_DEMO_PACE; do
  [ -n "${!k:-}" ] && ENV_VARS="${ENV_VARS:+$ENV_VARS,}$k=${!k}"
done

# The live trace streams from the instance running the audit, so keep to one instance and
# turn on session affinity. Plenty for a demo; see README "Scaling beyond the demo".
gcloud run deploy "$SERVICE" \
  --project "$PROJECT" --region "$REGION" --source . \
  --service-account "$SA" \
  --allow-unauthenticated \
  --memory 1Gi --cpu 1 --timeout 300 \
  --min-instances 1 --max-instances 1 --session-affinity \
  --set-env-vars "$ENV_VARS"

gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format='value(status.url)'
