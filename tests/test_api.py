import asyncio
import os
import pathlib
import subprocess
import sys
import time

import httpx
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "tests" / "samples" / "eicar.com"


@pytest.fixture(scope="session")
def servers():
    env = os.environ.copy()
    env["API_KEY"] = "demo-secret"

    stub = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "hybrid_analyzer_stub.api:app", "--port", "9000"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)  # stub first

    integ = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.api:app", "--port", "8000"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(2)  # let both bind
    yield {"stub": stub, "integ": integ}

    # teardown – portable terminate
    for p in (integ, stub):
        if p.poll() is None:
            p.terminate()
            p.wait(timeout=5)


async def wait_for_done(client: httpx.AsyncClient, sid: str, api_key="demo-secret"):
    headers = {"X-API-Key": api_key}
    for _ in range(10):  # ≈20 s max
        r = await client.get(f"/varist-get-report/{sid}", headers=headers)
        if r.status_code == 200 and r.json()["status"] == "done":
            return r.json()
        await asyncio.sleep(2)
    pytest.fail("Report never reached 'done'")



@pytest.mark.asyncio
async def test_health(servers):
    async with httpx.AsyncClient(base_url="http://localhost:8000") as c:
        r = await c.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_auth_failure(servers):
    async with httpx.AsyncClient(base_url="http://localhost:8000") as c:
        r = await c.get("/varist-get-report/bogus", headers={"X-API-Key": "wrong"})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_happy_path(servers):
    async with httpx.AsyncClient(base_url="http://localhost:8000") as c:
        headers = {"X-API-Key": "demo-secret"}
        with open(SAMPLE, "rb") as f:
            r = await c.post("/varist-submit-file", headers=headers,
                             files={"file": (SAMPLE.name, f, "application/octet-stream")})
        assert r.status_code == 200
        sid = r.json()["submission_id"]

        rep = await wait_for_done(c, sid)
        assert rep["risk"] in {"critical", "high", "medium", "low"}


@pytest.mark.asyncio
async def test_unknown_sid(servers):
    async with httpx.AsyncClient(base_url="http://localhost:8000") as c:
        r = await c.get("/varist-get-report/does-not-exist",
                        headers={"X-API-Key": "demo-secret"})
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_forced_clean_verdict(servers):
    """
    Call the stub directly with ?verdict=clean to ensure 'clean/low' path works,
    then check the JSON shape.
    """
    async with httpx.AsyncClient(base_url="http://localhost:9000") as stub_client:
        with open(SAMPLE, "rb") as f:
            r = await stub_client.post("/scan?verdict=clean",
                                       files={"file": (SAMPLE.name, f, "application/octet-stream")})
        sid = r.json()["submission_id"]
        # poll stub directly
        for _ in range(6):
            rep = (await stub_client.get(f"/report/{sid}")).json()
            if rep["status"] == "done":
                assert rep["risk"] == "low"
                assert rep["verdict"] == "clean"
                break
            await asyncio.sleep(1)
        else:
            pytest.fail("Stub clean verdict never finished")



@pytest.fixture(scope="session")
def integration_only():
    """Start integration on 8002 pointing to a non-existent HA_URL."""
    env = os.environ.copy()
    env["API_KEY"] = "demo-secret"
    env["HA_URL"] = "http://localhost:9999"  # closed port

    integ = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.api:app", "--port", "8002"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(2)
    yield integ
    if integ.poll() is None:
        integ.terminate()
        integ.wait(timeout=5)


@pytest.mark.asyncio
async def test_stub_down_502(integration_only):
    async with httpx.AsyncClient(base_url="http://localhost:8002") as c:
        headers = {"X-API-Key": "demo-secret"}
        with open(SAMPLE, "rb") as f:
            r = await c.post("/varist-submit-file", headers=headers,
                             files={"file": (SAMPLE.name, f, "application/octet-stream")})
        sid = r.json()["submission_id"]

        # first poll should surface 502 (stored as 'failed')
        r = await c.get(f"/varist-get-report/{sid}", headers=headers)
        assert r.status_code == 502
