# ClaimShield AI - demo script (about 4 minutes)

**Before you start:** `make run` (or open the Cloud Run URL), with `CLAIMSHIELD_DEMO_PACE=0.35`. Open the BILL-001 PDF in a second tab.

## 1. The problem (30s)
"After a hospital stay, people get a 15-line bill and a settlement letter full of deductions. Hardly anyone checks either against their policy wording, and errors in both directions are common. ClaimShield is an auditor that works for the policyholder."

## 2. Run the headline case (90s)
- Click **Sunrise Multispeciality Hospital (appendectomy)**. Show the bill PDF briefly: the watermark says it's synthetic.
- Press **Audit**. While the trace runs, narrate it:
  - *Intake* parses the bill and the policy with Document AI and loads the line items into BigQuery.
  - *Policy* runs a Vertex AI Search query per topic (room rent, co-pay, sub-limits, consumables) and pulls the governing clause, with a citation.
  - *Audit* and *Benchmark* run **in parallel** (an ADK ParallelAgent): SQL checks for duplicates and arithmetic, then a replay of the insurer's settlement under the policy terms.
  - *Reconciliation* computes what you should owe. *Dispute* writes the letters.

## 3. Walk through the findings (60s)
- Headline: **you paid ₹25,746 and should owe ₹900, so the likely recovery is ₹24,846.**
- F1: the insurer took a **20% co-pay**, but the clause on screen (§3.2) says there's no co-pay at a network hospital. Expand the row to show the clause quote.
- F4: the **duplicate CBC**. Click "line 3" and the itemised bill highlights it.
- F5: the **Grade IV anaesthesia** for a routine appendectomy is marked *Worth reviewing*, not "fraud". It could be justified, so the letter asks for the anaesthesia record.
- Point out what was *not* flagged: attendant food was correctly excluded under §4.4.

## 4. Letters and report (30s)
- Show the letter **to the insurer** (cites §3.2 and §3.4, asks for ₹24,846, invokes the grievance clause §5.2) and the letter **to the hospital**.
- Open the reconciliation report PDF.

## 5. Precision (20s)
- Click **Audit another bill**, choose **Sanjeevani Hospital (clean bill)**, and press Audit.
- "Repeat CBCs on different days, a correct 20% co-pay, a correctly excluded admission kit: **nothing worth disputing**." This shows it doesn't over-flag.

## 6. Close (20s)
"Detection and money math are deterministic, so every number is reproducible and tested against an answer key. Gemini handles the language and is guarded so it can't invent amounts. It runs on ADK, Document AI, Vertex AI Search, BigQuery, Gemini and Cloud Run."

**Backup if Wi-Fi or cloud fails:** set every `CLAIMSHIELD_USE_*` flag to false and restart. The same demo runs fully offline.
