"""Stub Hybrid-Analyzer that now returns richer metadata."""
import asyncio
import mimetypes
import os
import random
import time
from enum import Enum
from pathlib import Path
from typing import Dict, Optional
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile

class Verdict(str, Enum):
    malicious = "malicious"
    suspicious = "suspicious"
    clean = "clean"
    unknown = "unknown"


RISK_MAP = {
    Verdict.malicious: "critical",
    Verdict.suspicious: "high",
    Verdict.unknown: "medium",
    Verdict.clean: "low",
}

REASON_MAP = {
    Verdict.malicious: "Matched EICAR signature",
    Verdict.suspicious: "High entropy sections",
    Verdict.clean: "No anomalies detected",
    Verdict.unknown: "Static analysis inconclusive",
}


app = FastAPI(title="Stub Hybrid Analyzer (rich)")

_store: Dict[str, dict] = {}

SEED = int(os.getenv("STUB_SEED", "42"))
random.seed(SEED)


async def _finish_job(sid: str, verdict: Verdict, started_at: float):
    await asyncio.sleep(3)  # emulate sandbox delay
    rec = _store[sid]
    rec.update(
        status="done",
        verdict=verdict,
        risk=RISK_MAP[verdict],
        scan_duration=round(time.time() - started_at, 2),
        reason=REASON_MAP[verdict],
        iocs=[
            {"type": "sha256", "value": uuid4().hex},
            {"type": "domain", "value": "bad.example.org"},
        ],
    )



@app.post("/scan")
async def scan(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    verdict: Optional[Verdict] = Query(
        None, description="Force a verdict for deterministic demos"
    ),
):
    """Accept a file and schedule analysis."""
    raw_bytes = await file.read()  # read immediately – keeps UploadFile open
    sid = str(uuid4())
    submitted_ts = int(time.time())

    _store[sid] = {
        "file_name": file.filename,
        "file_type": mimetypes.guess_type(file.filename)[0]
        or "application/octet-stream",
        "file_size": len(raw_bytes),
        "submitted": submitted_ts,
        "status": "running",
    }

    verdict = verdict or random.choice(list(Verdict))
    background_tasks.add_task(_finish_job, sid, verdict, time.time())
    return {"submission_id": sid, "status": "running"}


@app.get("/report/{sid}")
def report(sid: str):
    if sid not in _store:
        raise HTTPException(status_code=404, detail="Unknown submission id")
    return _store[sid]
