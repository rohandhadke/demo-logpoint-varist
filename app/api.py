from uuid import uuid4
import logging
import aiohttp
from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    Header,
    HTTPException,
    UploadFile,
    status,
)

from .settings import settings
from .models import SubmitResponse, ReportResponse
from .storage import store


logger = logging.getLogger("varist-demo")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

app = FastAPI(title="Varist ↔ Logpoint Demo (Improved)")


def _check_api_key(key: str) -> None:
    if key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid X-API-Key",
        )


@app.get("/health")
def health():
    return {"status": "ok"}



@app.post("/varist-submit-file", response_model=SubmitResponse)
async def varist_submit_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    _check_api_key(x_api_key)

    submission_id = str(uuid4())

    await store.save(
        submission_id,
        {"submission_id": submission_id, "status": "running"},
    )

    file_bytes = await file.read()
    filename = file.filename

    async def forward_to_ha(payload: bytes, name: str):
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=settings.request_timeout)
            ) as session:
                data = aiohttp.FormData()
                data.add_field("file", payload, filename=name)
                async with session.post(f"{settings.ha_url}/scan", data=data) as resp:
                    resp.raise_for_status()
                    ha = await resp.json()

            await store.update(
                submission_id,
                ha_id=ha["submission_id"],
                status="running",
            )
        except Exception as exc:
            logger.exception("Forwarding to HA failed: %s", exc)
            await store.update(
                submission_id,
                status="failed",
                error=str(exc),
            )

    background_tasks.add_task(forward_to_ha, file_bytes, filename)
    return SubmitResponse(submission_id=submission_id, status="running")


@app.get("/varist-get-report/{submission_id}", response_model=ReportResponse)
async def varist_get_report(
    submission_id: str,
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    _check_api_key(x_api_key)

    cached = await store.get(submission_id)
    if not cached:
        raise HTTPException(status_code=404, detail="Unknown submission_id")

    if cached["status"] == "done":
        return cached
    if cached["status"] == "failed":
        raise HTTPException(status_code=502, detail=cached["error"])

    # Poll Hybrid Analyzer stub for latest status
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=settings.request_timeout)
        ) as session:
            async with session.get(
                f"{settings.ha_url}/report/{cached['ha_id']}"
            ) as resp:
                resp.raise_for_status()
                report = await resp.json()
    except Exception as exc:
        logger.error("Error fetching HA report: %s", exc)
        raise HTTPException(
            status_code=502, detail="HybridAnalyzer unreachable"
        ) from exc

    if report["status"] == "done":
        await store.update(submission_id, **report)

    return await store.get(submission_id)