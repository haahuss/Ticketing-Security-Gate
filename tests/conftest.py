import os
import pytest_asyncio
import httpx
from redis.asyncio import Redis

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

@pytest_asyncio.fixture(scope="function")
async def client():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as c:
        yield c

@pytest_asyncio.fixture(autouse=True, scope="function")
async def clean_redis():
    r = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        await r.flushdb()
        await r.set("cfg:offline_mode", "false")
        yield
    finally:
        await r.aclose()
