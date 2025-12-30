import os
import asyncio
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from .db import SessionLocal, engine, Base
from .models import Redemption, AuditLog

Base.metadata.create_all(bind=engine)

redis = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)

async def offline_enabled() -> bool:
    val = await redis.get("cfg:offline_mode")
    return (val or "false").lower() == "true"

async def main():
    # resume where we left off (so backlog gets processed after offline)
    last_id = await redis.get("worker:last_id") or "0-0"

    while True:
        if await offline_enabled():
            await asyncio.sleep(1.0)
            continue

        resp = await redis.xread({"offline_validations": last_id}, block=5000, count=50)
        if not resp:
            continue

        _, messages = resp[0]
        for msg_id, data in messages:
            last_id = msg_id
            await process_one(data)
            await redis.xdel("offline_validations", msg_id)

            # persist progress
            await redis.set("worker:last_id", last_id)


async def process_one(data: dict):
    decision_id = data["decision_id"]
    event_id = data["event_id"]
    ticket_id = data["ticket_id"]
    ip = data.get("ip", "unknown")
    ua = data.get("ua", "")

    # Optional: helpful demo logs
    print(f"[worker] syncing decision_id={decision_id} ticket_id={ticket_id} event_id={event_id}")

    db = SessionLocal()
    try:
        db.add(Redemption(ticket_id=ticket_id, event_id=event_id))
        db.add(AuditLog(
            decision_id=decision_id,
            ip=ip,
            user_agent=ua,
            event_id=event_id,
            ticket_id=ticket_id,
            status="ACCEPTED",
            reason_code="OK_SYNCED",
        ))
        db.commit()
    except IntegrityError:
        db.rollback()
        # Optional: helpful demo logs
        print(f"[worker] replay_on_sync ticket_id={ticket_id} event_id={event_id}")

        db.add(AuditLog(
            decision_id=decision_id,
            ip=ip,
            user_agent=ua,
            event_id=event_id,
            ticket_id=ticket_id,
            status="REJECTED",
            reason_code="REPLAY_ON_SYNC",
        ))
        db.commit()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(main())
