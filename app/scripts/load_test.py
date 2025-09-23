"""Simple load testing helper for exercising FusionX endpoints.

Run with `python -m app.scripts.load_test` while the server is running.
"""

import asyncio
import os

import httpx

BASE_URL = os.getenv("FUSIONX_BASE_URL", "http://127.0.0.1:8000")
USERNAME = os.getenv("FUSIONX_USER", "chef")
PASSWORD = os.getenv("FUSIONX_PASSWORD", "password")


async def login(client: httpx.AsyncClient) -> str:
    resp = await client.post(
        f"{BASE_URL}/api/mobile/login", json={"username": USERNAME, "password": PASSWORD}
    )
    resp.raise_for_status()
    return resp.json()["token"]


async def run_iteration(client: httpx.AsyncClient, token: str) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    await client.get(f"{BASE_URL}/healthz")
    await client.get(f"{BASE_URL}/api/mobile/locations", headers=headers)
    await client.get(f"{BASE_URL}/api/mobile/trucks", headers=headers)


async def main(iterations: int = 25, concurrency: int = 5) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        token = await login(client)

        async def worker() -> None:
            for _ in range(iterations):
                await run_iteration(client, token)

        await asyncio.gather(*[worker() for _ in range(concurrency)])


if __name__ == "__main__":
    asyncio.run(main())
