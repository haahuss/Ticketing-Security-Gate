import time

async def token_bucket(redis, key: str, capacity: int, refill_per_sec: float) -> bool:
    now = time.time()
    bucket_key = f"rl:{key}"

    # Lua would be better; keep it simple today:
    data = await redis.hgetall(bucket_key)
    tokens = float(data.get(b"tokens", capacity))
    last = float(data.get(b"last", now))

    # Refill
    tokens = min(capacity, tokens + (now - last) * refill_per_sec)

    if tokens < 1.0:
        await redis.hset(bucket_key, mapping={"tokens": tokens, "last": now})
        await redis.expire(bucket_key, 3600)
        return False

    tokens -= 1.0
    await redis.hset(bucket_key, mapping={"tokens": tokens, "last": now})
    await redis.expire(bucket_key, 3600)
    return True
