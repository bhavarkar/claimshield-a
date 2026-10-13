# ClaimShield AI

**An agentic hospital-bill and insurance-claim auditor that works for the policyholder.**
Upload a hospital bill and an insurance policy. ClaimShield's agents audit the bill line by line against the policy wording and return:

- findings, each with the exact bill line, the exact policy clause, a plain-language explanation, a confidence label (**High** / **Worth reviewing**) and the rupee impact
- a reconciliation of billed vs covered vs owed, and how much you can likely recover
- ready-to-send dispute letters (one to the insurer, one to the hospital) and a PDF reconciliation report

Built for the Google Cloud AI hackathon, **BFSI theme** (intelligent risk, fraud and financial experiences). Flags are always framed as *worth disputing*, never as fraud.

---

## What it detects

| Check | How | Confidence |
|---|---|---|
| Duplicate charges | SQL window over (date, code, qty, price) | High; Worth reviewing for pharmacy/therapy, where repeats can be legitimate |
| Quantity x rate errors | SQL `qty * unit_price <> amount` | High |
| Room days beyond the length of stay | admission/discharge dates vs room quantity | High |
| Gross total ≠ sum of lines | totals reconciliation | High |
| Settlement differs from the policy (co-pay, sub-limit, room-rent cap, wrongly excluded items) | **policy replay**: the insurer's parameters are read back from its printed deductions, then each one is swapped for the policy's value in turn. Each finding's impact is that step's change in payout, so the impacts add up exactly to the total shortfall | High |
| Possible upcoding | SQL: billed complexity tier vs the typical tier for the procedure | Worth reviewing |
| Price far above benchmark | SQL: unit price > 1.3x the 90th-percentile reference price | Worth reviewing |
| Clinical consistency (Gemini mode only) | Gemini review of lines vs diagnosis | Worth reviewing |

**Design choice:** detection and money math are deterministic, so they are reproducible and testable. Gemini handles the language: plain-language explanations, letter drafting, cross-checking extracted policy terms, transcribing unfamiliar bill layouts, and an optional clinical review. Gemini output is guarded: if a drafted letter or explanation contains a rupee amount that isn't in the evidence, it is discarded and the template text is used.

## Architecture

```
Browser (web/)  --POST /api/audit-->  FastAPI on Cloud Run  --SSE /events-->  live agent trace
                                          |
                    ADK  claimshield_orchestrator (SequentialAgent)
                      ├─ intake_agent          Document AI -> normalised bill + policy JSON; rows -> BigQuery
                      ├─ policy_agent          Vertex AI Search -> governing clauses -> structured terms (+ Gemini cross-check)
                      ├─ findings_team (ParallelAgent)
                      │    ├─ audit_agent      duplicates / arithmetic / stay / totals SQL + policy replay
                      │    └─ benchmark_agent  reference-pricing + upcoding SQL
                      ├─ reconciliation_agent  billed vs covered vs owed; likely and upper-bound recovery
                      └─ dispute_agent         Gemini explanations + letters; report PDFs -> Cloud Storage
```

Agents pass results through ADK session state (`EventActions.state_delta`). Every step writes to a per-case trace. The UI streams it live, and each event is also logged as one JSON line, which Cloud Run ships to Cloud Logging.

**Every Google Cloud service has a local fallback**, chosen per service by a flag. If a flagged service fails to initialise, the local fallback takes over and the trace says so, so a missing credential can't take the demo down:

| Concern | Google Cloud | Local fallback |
|---|---|---|
| Parsing | Document AI Form Parser | pdfplumber |
| Warehouse + audit SQL | BigQuery | in-memory SQLite (same SQL files) |
| Clause retrieval | Vertex AI Search (chunked) | BM25 over parsed clauses |
| Reasoning / drafting | Gemini on Vertex AI | deterministic templates |
| Files | Cloud Storage | `var/` directory |
| Orchestration | ADK (also locally) | plain Python runner |

## Folder structure

```
claimshield/
  agents/      steps.py (the six agents' logic) · adk_agents.py (ADK graph) · runner.py
  domain/      coverage.py (entitlement engine + policy replay) · policy_terms.py
  services/    parsing.py · store.py · retrieval.py · llm.py · storage.py · __init__.py (fallback wiring)
  sql/         duplicates · arithmetic · benchmark_outliers · upcoding · schema_bigquery
  reports/     pdf.py (reconciliation report + letters)
  api/main.py  FastAPI + static UI
web/           index.html · app.js · styles.css (no build step)
data/
  generate.py  synthetic bills/policies generator (with planted issues)
  reference/   reference_pricing.csv · procedure_benchmarks.csv
  samples/     generated PDFs · catalog.json · expected.json (answer key)
scripts/       run_samples.py · setup_gcp.sh · load_bigquery.py · index_policies.py · deploy_cloud_run.sh
tests/         answer-key E2E tests (ADK and plain runners), API tests, Gemini guard tests
docs/          DEMO_SCRIPT.md
```

## Run locally (no cloud credentials needed)

```bash
make setup                 # python3.11 venv + deps
cp .env.example .env       # all cloud flags false by default
make test                  # 21 tests: answer key, money math, API, guards
make samples               # run all 4 synthetic bills, print findings
make run                   # http://localhost:8080
```

Open the UI, pick a sample case (or upload a bill and a policy PDF) and press **Audit**. `CLAIMSHIELD_DEMO_PACE=0.35` in `.env` slows the trace so it can be followed live. Local mode otherwise finishes in about a second.

To run in Docker instead: `make docker`.

## Synthetic data

`python data/generate.py` regenerates everything. All people, hospitals, insurers and policy numbers are fictional, and every PDF is watermarked *SYNTHETIC - FOR DEMO*.

| Bill | Policy | Planted issues | Result |
|---|---|---|---|
| BILL-001 Sunrise, appendectomy | Suraksha Gold | duplicate CBC; Ceftriaxone 6 x ₹180 billed ₹1,800; Grade IV anaesthesia for a routine case; 20% co-pay at a network hospital (policy: 0%); admission kit deducted though the policy covers consumables | recovery ₹24,846 |
| BILL-002 Netra, cataract | Suraksha Gold | eye drops 2 x ₹450 billed ₹1,350; gross total ₹1,000 above the lines; sub-limit applied at ₹35,000 (policy: ₹40,000) | recovery ₹6,450 |
| BILL-003 Lotus, knee replacement | CareFirst Silver | room billed 6 days for 5 nights; physio twice on the same day; MRI 1.6x the benchmark; sub-limit at ₹1,00,000 (policy: ₹1,50,000) | ₹42,800 likely, up to ₹49,100 |
| BILL-004 Sanjeevani, dengue | CareFirst Silver | **none (clean bill)**: repeat CBCs on different days, correct 20% co-pay, correctly excluded admission kit | **0 findings** |

Correctly applied exclusions (attendant food on BILL-001, gloves and masks on BILL-003) are deliberately *not* flagged.

## Deploy to Google Cloud

### Services to enable
Cloud Run, Cloud Build, Artifact Registry, Document AI, BigQuery, Vertex AI Search (Discovery Engine), Vertex AI (Gemini), Cloud Storage, Cloud Logging. `scripts/setup_gcp.sh` enables them all.

### Steps
```bash
gcloud auth login && gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=your-project GOOGLE_CLOUD_LOCATION=us-central1
make gcp-setup        # APIs, bucket, BigQuery dataset, service account + roles, Form Parser, search data store
                      # -> prints the .env values; paste them into .env
make bq-load          # tables + reference pricing into BigQuery
make index-policies   # sample policies -> GCS -> Vertex AI Search (indexing takes a few minutes)
make deploy           # Cloud Build + Cloud Run; prints the service URL
```

You can turn services on one at a time, e.g. only `CLAIMSHIELD_USE_GEMINI=true`, and check the badges in the UI header and the trace. Each one shows the backend actually used.

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | - | project id |
| `GOOGLE_CLOUD_LOCATION` | `us-central1` | Cloud Run + Gemini region |
| `CLAIMSHIELD_USE_DOCAI` / `DOCAI_LOCATION` / `DOCAI_PROCESSOR_ID` | `false` / `us` / - | Document AI Form Parser |
| `CLAIMSHIELD_USE_BIGQUERY` / `BQ_DATASET` | `false` / `claimshield` | BigQuery warehouse |
| `CLAIMSHIELD_USE_VERTEX_SEARCH` / `VERTEX_SEARCH_LOCATION` / `VERTEX_SEARCH_DATASTORE_ID` | `false` / `global` / `claimshield-policies` | clause retrieval |
| `CLAIMSHIELD_USE_GEMINI` / `GEMINI_MODEL` | `false` / `gemini-2.5-flash` | reasoning + drafting |
| `CLAIMSHIELD_USE_GCS` / `GCS_BUCKET` | `false` / - | uploads + reports |
| `CLAIMSHIELD_USE_ADK` | `true` | ADK orchestration (plain runner if `false` or ADK missing) |
| `CLAIMSHIELD_OUTLIER_RATIO` | `1.3` | benchmark threshold (x p90) |
| `CLAIMSHIELD_DEMO_PACE` | `0` | seconds to pause per trace step |

## What has and hasn't been verified

- **Verified locally:** the full pipeline through ADK `InMemoryRunner` and the plain runner on all four bills, matched against the answer key; reconciliation amounts; the HTTP API including uploads and validation; PDF generation; the UI, rendered in headless Chrome; and the Gemini guardrails (with a stubbed model).
- **Written but not yet run against real Google Cloud**, because no project was available while building: the Document AI, BigQuery, Vertex AI Search, Gemini and Cloud Storage adapters, plus `setup_gcp.sh`, `index_policies.py` and `deploy_cloud_run.sh`. The SQL is written in the subset both engines accept (including integer casts, since BigQuery can't partition on FLOAT64). Expect small fixes on first contact, and try one flag at a time.
- **Vertex AI Agent Engine:** the agent graph (`claimshield/agents/adk_agents.py: root_agent`) passes everything through session state, so it can be deployed there. That isn't scripted yet because the demo serves from Cloud Run.

## Limits and next steps

- The local parser expects an itemised table with Qty and Amount columns. With Gemini on, unfamiliar layouts are transcribed by Gemini instead.
- Benchmarks and procedure tiers are a small synthetic table. A real deployment would use regional tariff data such as PM-JAY/CGHS package rates.
- Scaling beyond the demo: the live trace lives in instance memory, so the deploy pins one instance with session affinity. To scale, move traces to Firestore or Pub/Sub, and the audit itself to Cloud Run Jobs or Cloud Tasks.
