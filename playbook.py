"""CLI that mimics a Logpoint SOAR playbook."""
import argparse
import asyncio
import time
from pathlib import Path

import aiohttp


async def run(file_path: Path, base_url: str, api_key: str, interval: float, max_tries: int):
    headers = {"X-API-Key": api_key}
    async with aiohttp.ClientSession(headers=headers) as session:
        data = aiohttp.FormData()
        data.add_field("file", file_path.read_bytes(), filename=file_path.name)
        async with session.post(f"{base_url}/varist-submit-file", data=data) as r:
            r.raise_for_status()
            sid = (await r.json())["submission_id"]
            print(f"[{time.ctime()}] Submitted → {sid}")

        for attempt in range(max_tries):
            async with session.get(f"{base_url}/varist-get-report/{sid}") as r:
                r.raise_for_status()
                rep = await r.json()

            print(f"[{time.ctime()}] status={rep['status']}")
            if rep["status"] == "done":
                risk = rep["risk"]
                if risk in {"critical", "high"}:
                    print("⚠️  MALICIOUS/SUSPICIOUS – isolate host, block IOCs:")
                elif risk == "medium":
                    print("🔍 Needs analyst review:")
                else:
                    print("✅ Benign – close incident.")
                for ioc in rep.get("iocs", []):
                    print(f"   • {ioc['type']}: {ioc['value']}")
                break
            await asyncio.sleep(interval)
        else:
            print("Timed out waiting for report.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path, help="File to submit")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--api-key", default="demo-secret")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--max-tries", type=int, default=10)
    args = parser.parse_args()

    if not args.file.exists():
        raise SystemExit(f"File not found: {args.file}")
    asyncio.run(
        run(args.file, args.base_url, args.api_key, args.interval, args.max_tries)
    )
