import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import select

from jose import jwt

from .db import SessionLocal
from .models import Ticket, Event, Redemption, AuditLog

router = APIRouter(prefix="/admin", tags=["admin"])

SECRET = os.environ.get("TICKET_SIGNING_SECRET", "dev_secret_change_me")

WORDS = [
  "alpha","beta","gamma","delta","omega",
  "llama","panda","tiger","eagle","otter",
  "nova","comet","orbit","pixel","spark",
  "jade","ember","cobalt","onyx","ivory",
]


# --- Offline toggle stored in Redis via main.py's redis client ---
# We will call the existing /admin/offline endpoints from UI, so we keep them here,
# but we need a Redis client. We’ll reuse REDIS_URL.
from redis.asyncio import Redis
redis = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)


# -------------------------
# Helpers
# -------------------------
def _gen_event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:8]}"

def _gen_ticket_id(event_id: str, i: int) -> str:
    # evt_ab12cd34 -> ab12
    short = event_id.split("_")[-1][:4]
    word = WORDS[(i - 1) % len(WORDS)]
    # ticket-ab12-ivory-001
    return f"ticket-{short}-{word}-{i:03d}"



def _mint_token(ticket_id: str, event_id: str, org_id: str, ttl_minutes: int = 60) -> str:
    nonce = str(uuid.uuid4())
    exp = int((datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)).timestamp())
    payload = {
        "ticket_id": ticket_id,
        "event_id": event_id,
        "org_id": org_id,
        "nonce": nonce,
        "exp": exp,
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")


# -------------------------
# Event + Ticket APIs
# -------------------------
class CreateEventReq(BaseModel):
    name: str
    ticket_count: int
    org_id: str = "org_1"

@router.post("/events")
def create_event(req: CreateEventReq):
    if req.ticket_count < 1 or req.ticket_count > 5000:
        return {"ok": False, "error": "ticket_count must be between 1 and 5000"}

    event_id = _gen_event_id()

    db = SessionLocal()
    try:
        db.add(Event(id=event_id, name=req.name, org_id=req.org_id))

        tickets = []
        for i in range(1, req.ticket_count + 1):
            tickets.append(Ticket(id=_gen_ticket_id(event_id, i), event_id=event_id, org_id=req.org_id))


        db.add_all(tickets)
        db.commit()

        return {
            "ok": True,
            "event_id": event_id,
            "name": req.name,
            "ticket_count": req.ticket_count,
            "org_id": req.org_id,
        }
    finally:
        db.close()

@router.get("/events")
def list_events():
    db = SessionLocal()
    try:
        rows = db.execute(select(Event).order_by(Event.created_at.desc())).scalars().all()
        return [
            {
                "event_id": e.id,
                "name": e.name,
                "org_id": e.org_id,
                "created_at": str(e.created_at),
            }
            for e in rows
        ]
    finally:
        db.close()

@router.get("/events/{event_id}/tickets")
def list_tickets(event_id: str, limit: int = 500):
    db = SessionLocal()
    try:
        tickets = db.execute(
            select(Ticket).where(Ticket.event_id == event_id).limit(limit)
        ).scalars().all()

        redeemed_rows = db.execute(
            select(Redemption.ticket_id, Redemption.redeemed_at).where(Redemption.event_id == event_id)
        ).all()
        redeemed_map = {tid: str(ts) for (tid, ts) in redeemed_rows}

        return [
            {
                "ticket_id": t.id,
                "event_id": t.event_id,
                "org_id": t.org_id,
                "status": "REDEEMED" if t.id in redeemed_map else "UNUSED",
                "redeemed_at": redeemed_map.get(t.id),
            }
            for t in tickets
        ]
    finally:
        db.close()


# -------------------------
# Scan ticket (operator UX)
# -------------------------
class ScanReq(BaseModel):
    event_id: str
    ticket_id: str
    org_id: str = "org_1"
    ttl_minutes: int = 60

@router.post("/scan")
async def scan_ticket(req: ScanReq, request: Request):
    """
    Operator scan endpoint:
    UI submits (event_id, ticket_id) only.
    Backend mints a JWT and calls /validate internally so we exercise the real gate.
    """
    token = _mint_token(req.ticket_id, req.event_id, req.org_id, ttl_minutes=req.ttl_minutes)

    # Call the local API container itself. This runs inside the api container.
    base = "http://127.0.0.1:8000"
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{base}/validate",
            json={"qr_token": token, "event_id": req.event_id},
            headers={"Content-Type": "application/json"},
            timeout=5.0,
        )
        return r.json()


# -------------------------
# Offline mode toggle
# -------------------------
class OfflineReq(BaseModel):
    enabled: bool

@router.post("/offline")
async def set_offline(req: OfflineReq):
    await redis.set("cfg:offline_mode", "true" if req.enabled else "false")
    return {"offline": req.enabled}

@router.get("/offline")
async def get_offline():
    val = await redis.get("cfg:offline_mode")
    return {"offline": (val or "false").lower() == "true"}


# -------------------------
# Logs
# -------------------------
@router.get("/audit")
def get_audit(limit: int = 80, event_id: Optional[str] = None):
    db = SessionLocal()
    try:
        q = db.query(AuditLog, Event).join(Event, Event.id == AuditLog.event_id, isouter=True)
        if event_id:
            q = q.filter(AuditLog.event_id == event_id)
        rows = q.order_by(AuditLog.created_at.desc()).limit(limit).all()

        out = []
        for log, ev in rows:
            out.append({
                "created_at": str(log.created_at),
                "ticket_id": log.ticket_id,
                "event_id": log.event_id,
                "event_name": ev.name if ev else None,
                "status": log.status,
                "reason_code": log.reason_code,
                "decision_id": log.decision_id,
            })
        return out
    finally:
        db.close()

