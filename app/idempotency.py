import json

async def get_cached_response(redis, idem_key: str):
    raw = await redis.get(f"idem:{idem_key}")
    return json.loads(raw) if raw else None

async def set_cached_response(redis, idem_key: str, response: dict, ttl_seconds: int = 300):
    await redis.setex(f"idem:{idem_key}", ttl_seconds, json.dumps(response))
