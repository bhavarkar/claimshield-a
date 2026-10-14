"""HTTP API and static web UI (one Cloud Run service).

    POST /api/audit                      start an audit (upload bill + policy PDFs, or pick samples)
    GET  /api/cases/{id}/events          live agent trace (Server-Sent Events)
    GET  /api/cases/{id}                 findings, reconciliation, letters
    GET  /api/cases/{id}/files/{name}    reconciliation report / dispute letter PDFs
    GET  /api/samples                    synthetic demo bills and policies
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
import warnings
from pathlib import Path
from typing import Any, Optional

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="google")

from fastapi import FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from ..agents.runner import run_audit  # noqa: E402
from ..config import PROJECT_ROOT  # noqa: E402
from ..services import get_services  # noqa: E402
from ..services.parsing import looks_like_pdf  # noqa: E402
from ..trace import TRACES  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("claimshield.api")

MAX_UPLOAD = 15 * 1024 * 1024
CASE_ID = re.compile(r"^[a-z0-9-]{6,64}$")
ARTIFACT_FILES = {
    "reconciliation_report.pdf": "report",
    "dispute_letter_insurer.pdf": "letter_insurer",
    "dispute_letter_hospital.pdf": "letter_hospital",
}

app = FastAPI(title="ClaimShield AI", version="0.1.0")
CASES: dict[str, dict[str, Any]] = {}
_TASKS: set[asyncio.Task] = set()


def _catalog() -> dict[str, Any]:
    return json.loads((get_services().settings.data_dir / "samples" / "catalog.json").read_text())


@app.get("/api/health")
def health() -> dict[str, Any]:
    svc = get_services()
    return {"status": "ok", "stack": svc.describe(), "warnings": svc.warnings}


@app.get("/api/samples")
def samples() -> dict[str, Any]:
    cat = _catalog()
    for bid, b in cat["bills"].items():
        b["id"] = bid
        b["url"] = f"/api/samples/{b['file']}"
        b["policy_plan"] = cat["policies"][b["policy"]]["plan"]
    for pid, p in cat["policies"].items():
        p["id"] = pid
        p["url"] = f"/api/samples/{p['file']}"
    return cat


@app.get("/api/samples/{kind}/{name}")
def sample_file(kind: str, name: str) -> FileResponse:
    if kind not in ("bills", "policies") or not re.fullmatch(r"[a-z0-9_]+\.pdf", name):
        raise HTTPException(404)
    path = get_services().settings.data_dir / "samples" / kind / name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="application/pdf")


async def _read_upload(upload: UploadFile, label: str) -> bytes:
    data = await upload.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, f"The {label} is larger than 15 MB.")
    if not looks_like_pdf(data):
        raise HTTPException(415, f"The {label} must be a PDF.")
    return data


@app.post("/api/audit")
async def start_audit(
    bill: Optional[UploadFile] = File(None),
    policy: Optional[UploadFile] = File(None),
    sample_bill: Optional[str] = Form(None),
    sample_policy: Optional[str] = Form(None),
) -> dict[str, str]:
    svc = get_services()
    cat = _catalog()
    samples_dir = svc.settings.data_dir / "samples"

    if bill is not None and bill.filename:
        bill_bytes, bill_name = await _read_upload(bill, "bill"), Path(bill.filename).name
    elif sample_bill in cat["bills"]:
        entry = cat["bills"][sample_bill]
        bill_bytes, bill_name = (samples_dir / entry["file"]).read_bytes(), Path(entry["file"]).name
        sample_policy = sample_policy or entry["policy"]
    else:
        raise HTTPException(400, "Upload a bill PDF or choose a sample bill.")

    if policy is not None and policy.filename:
        policy_bytes, policy_name = await _read_upload(policy, "policy"), Path(policy.filename).name
    elif sample_policy in cat["policies"]:
        entry = cat["policies"][sample_policy]
        policy_bytes, policy_name = (samples_dir / entry["file"]).read_bytes(), Path(entry["file"]).name
    else:
        raise HTTPException(400, "Upload a policy PDF or choose a sample policy.")

    case_id = f"case-{time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
    bill_key, policy_key = f"cases/{case_id}/bill.pdf", f"cases/{case_id}/policy.pdf"
    await asyncio.to_thread(svc.storage.put, bill_key, bill_bytes, "application/pdf")
    await asyncio.to_thread(svc.storage.put, policy_key, policy_bytes, "application/pdf")
    TRACES.create(case_id)
    CASES[case_id] = {"case_id": case_id, "status": "running", "bill_name": bill_name, "policy_name": policy_name}

    async def work() -> None:
        state = await run_audit(case_id, bill_key, policy_key, bill_name, policy_name)
        CASES[case_id] = state
        try:
            await asyncio.to_thread(svc.storage.put, f"cases/{case_id}/case.json",
                                    json.dumps(state, default=str).encode(), "application/json")
        except Exception:  # noqa: BLE001 - the in-memory copy still serves this instance
            log.exception("could not persist case %s", case_id)

    task = asyncio.create_task(work())
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return {"case_id": case_id}


def _case(case_id: str) -> dict[str, Any]:
    if not CASE_ID.match(case_id):
        raise HTTPException(404)
    if case_id in CASES:
        return CASES[case_id]
    svc = get_services()
    key = f"cases/{case_id}/case.json"
    if svc.storage.exists(key):
        CASES[case_id] = json.loads(svc.storage.get(key))
        return CASES[case_id]
    raise HTTPException(404, "Unknown case")


@app.get("/api/cases/{case_id}/events")
async def events(case_id: str) -> StreamingResponse:
    case = _case(case_id)

    async def stream():
        if case.get("status") != "running" and "trace" in case:
            for e in case["trace"]:
                yield f"data: {json.dumps(e)}\n\n"
            yield "event: end\ndata: {}\n\n"
            return
        trace = TRACES.get(case_id)
        cursor, last_beat = 0, time.monotonic()
        while True:
            batch = trace.since(cursor)
            for e in batch:
                yield f"data: {json.dumps(e, default=str)}\n\n"
            cursor += len(batch)
            if trace.finished and not trace.since(cursor):
                # The pipeline is done; wait for the case record to land before telling the UI.
                for _ in range(50):
                    if CASES.get(case_id, {}).get("status") != "running":
                        break
                    await asyncio.sleep(0.1)
                yield "event: end\ndata: {}\n\n"
                return
            if time.monotonic() - last_beat > 10:
                yield ": keep-alive\n\n"
                last_beat = time.monotonic()
            await asyncio.sleep(0.15)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/cases/{case_id}")
def case(case_id: str) -> JSONResponse:
    c = _case(case_id)
    if c.get("status") == "running":
        return JSONResponse({"case_id": case_id, "status": "running"})
    keep = ("case_id", "status", "error", "bill", "policy_doc", "policy_terms", "findings", "reconciliation", "letters", "stack", "bill_name", "policy_name")
    out = {k: c.get(k) for k in keep if k in c}
    out["files"] = {name: f"/api/cases/{case_id}/files/{name}" for name, key in ARTIFACT_FILES.items() if key in c.get("artifacts", {})}
    if isinstance(out.get("bill"), dict):
        # Do not mutate the stored case: responses must be read-only snapshots.
        out["bill"] = {key: value for key, value in out["bill"].items() if key != "parser"}
    return JSONResponse(out)


@app.get("/api/cases/{case_id}/files/{name}")
def case_file(case_id: str, name: str) -> Response:
    c = _case(case_id)
    if name not in ARTIFACT_FILES or ARTIFACT_FILES[name] not in c.get("artifacts", {}):
        raise HTTPException(404)
    data = get_services().storage.get(f"cases/{case_id}/{name}")
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{case_id}-{name}"'})


@app.get("/api/cases/{case_id}/letters/{recipient}.txt")
def letter_text(case_id: str, recipient: str) -> PlainTextResponse:
    c = _case(case_id)
    for letter in c.get("letters", []):
        if letter["recipient"] == recipient:
            return PlainTextResponse(f"To,\n{letter['to']}\n\nSubject: {letter['subject']}\n\n{letter['body']}\n",
                                     headers={"Content-Disposition": f'attachment; filename="{case_id}-letter-{recipient}.txt"'})
    raise HTTPException(404)


app.mount("/", StaticFiles(directory=PROJECT_ROOT / "web", html=True), name="web")
