import os, uuid
from fastapi import FastAPI, Header, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError

from .db import SessionLocal, engine, Base
from .models import Ticket, Redemption, AuditLog
from .security import verify_qr_token
from .rate_limit import token_bucket
from .idempotency import get_cached_response, set_cached_response
from .admin import router as admin_router

# --- Config / globals ---
REDIS_URL = os.environ["REDIS_URL"]
SECRET = os.environ["TICKET_SIGNING_SECRET"]
DEFAULT_OFFLINE_MODE = os.environ.get("OFFLINE_MODE", "false").lower() == "true"

# Create FastAPI app FIRST
app = FastAPI(title="Ticket Security Gate", version="1.0.0")

# Create Redis client after config is available
redis = Redis.from_url(REDIS_URL, decode_responses=False)

# Mount UI + Admin routes AFTER app exists
app.mount("/ui", StaticFiles(directory="app/ui", html=True), name="ui")
app.include_router(admin_router)

# Create DB tables (fine to do at import-time for demo)
Base.metadata.create_all(bind=engine)

async def is_offline_mode() -> bool:
    val = await redis.get("cfg:offline_mode")
    if val is None:
        return DEFAULT_OFFLINE_MODE
    return val.decode("utf-8").lower() == "true"

class ValidateReq(BaseModel):
    qr_token: str
    event_id: str

@app.post("/validate")
async def validate_ticket(
    req: ValidateReq,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    decision_id = str(uuid.uuid4())
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")

    # Idempotency
    if idempotency_key:
        cached = await get_cached_response(redis, idempotency_key)
        if cached:
            return cached

    # Rate limit (10 requests/min per IP)
    allowed = await token_bucket(redis, key=ip, capacity=10, refill_per_sec=10/60)
    if not allowed:
        resp = {"status": "REJECTED", "reason_code": "RATE_LIMITED", "ticket_id": None, "decision_id": decision_id}
        if idempotency_key:
            await set_cached_response(redis, idempotency_key, resp)
        await _audit(decision_id, ip, ua, req.event_id, None, resp["status"], resp["reason_code"])
        return resp

    # Verify token
    try:
        payload = verify_qr_token(req.qr_token, SECRET)
    except ValueError as e:
        resp = {"status": "REJECTED", "reason_code": str(e), "ticket_id": None, "decision_id": decision_id}
        if idempotency_key:
            await set_cached_response(redis, idempotency_key, resp)
        await _audit(decision_id, ip, ua, req.event_id, None, resp["status"], resp["reason_code"])
        return resp

    ticket_id = payload["ticket_id"]
    token_event_id = payload["event_id"]
    nonce = payload["nonce"]

    if token_event_id != req.event_id:
        resp = {"status": "REJECTED", "reason_code": "WRONG_EVENT", "ticket_id": ticket_id, "decision_id": decision_id}
        if idempotency_key:
            await set_cached_response(redis, idempotency_key, resp)
        await _audit(decision_id, ip, ua, req.event_id, ticket_id, resp["status"], resp["reason_code"])
        return resp

    # Replay protection (fast path): nonce can be seen once
    replay_key = f"replay:{req.event_id}:{nonce}"
    first = await redis.setnx(replay_key, "1")
    await redis.expire(replay_key, 60 * 60 * 12)  # 12h TTL for event day
    if not first:
        resp = {"status": "REJECTED", "reason_code": "REPLAY", "ticket_id": ticket_id, "decision_id": decision_id}
        if idempotency_key:
            await set_cached_response(redis, idempotency_key, resp)
        await _audit(decision_id, ip, ua, req.event_id, ticket_id, resp["status"], resp["reason_code"])
        return resp

    # Offline-like simulation: enqueue if offline
    if await is_offline_mode():
        await redis.xadd(
            "offline_validations",
            {"decision_id": decision_id, "event_id": req.event_id, "ticket_id": ticket_id, "ip": ip, "ua": ua},
        )
        resp = {"status": "PENDING_SYNC", "reason_code": "SYSTEM_OFFLINE", "ticket_id": ticket_id, "decision_id": decision_id}
        if idempotency_key:
            await set_cached_response(redis, idempotency_key, resp)
        await _audit(decision_id, ip, ua, req.event_id, ticket_id, "PENDING_SYNC", "SYSTEM_OFFLINE")
        return resp

    # Durable enforcement in DB
    db = SessionLocal()
    try:
        t = db.get(Ticket, ticket_id)
        if not t:
            resp = {"status": "REJECTED", "reason_code": "INVALID_TOKEN", "ticket_id": ticket_id, "decision_id": decision_id}
            if idempotency_key:
                await set_cached_response(redis, idempotency_key, resp)
            await _audit(decision_id, ip, ua, req.event_id, ticket_id, resp["status"], resp["reason_code"])
            return resp

        db.add(Redemption(ticket_id=ticket_id, event_id=req.event_id))
        db.add(AuditLog(decision_id=decision_id, ip=ip, user_agent=ua, event_id=req.event_id, ticket_id=ticket_id, status="ACCEPTED", reason_code="OK"))
        db.commit()

        resp = {"status": "ACCEPTED", "reason_code": "OK", "ticket_id": ticket_id, "decision_id": decision_id}
        if idempotency_key:
            await set_cached_response(redis, idempotency_key, resp)
        return resp

    except IntegrityError:
        db.rollback()
        resp = {"status": "REJECTED", "reason_code": "REPLAY", "ticket_id": ticket_id, "decision_id": decision_id}
        if idempotency_key:
            await set_cached_response(redis, idempotency_key, resp)
        await _audit(decision_id, ip, ua, req.event_id, ticket_id, resp["status"], resp["reason_code"])
        return resp

    except Exception:
        db.rollback()
        await redis.xadd(
            "offline_validations",
            {"decision_id": decision_id, "event_id": req.event_id, "ticket_id": ticket_id, "ip": ip, "ua": ua},
        )
        resp = {"status": "PENDING_SYNC", "reason_code": "SYSTEM_OFFLINE", "ticket_id": ticket_id, "decision_id": decision_id}
        if idempotency_key:
            await set_cached_response(redis, idempotency_key, resp)
        await _audit(decision_id, ip, ua, req.event_id, ticket_id, "PENDING_SYNC", "SYSTEM_OFFLINE")
        return resp

    finally:
        db.close()

async def _audit(decision_id: str, ip: str, ua: str, event_id: str, ticket_id: str | None, status: str, reason: str):
    try:
        db = SessionLocal()
        db.add(AuditLog(decision_id=decision_id, ip=ip, user_agent=ua, event_id=event_id, ticket_id=ticket_id, status=status, reason_code=reason))
        db.commit()
    except Exception:
        pass
    finally:
        try:
            db.close()
        except Exception:
            pass
