import pytest
from jose import jwt
from datetime import datetime, timedelta, timezone
import uuid
import os

pytestmark = pytest.mark.asyncio

def mint_token(secret, ticket_id, event_id, org_id="org_1", ttl_minutes=60):
    exp = int((datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)).timestamp())
    payload = {"ticket_id": ticket_id, "event_id": event_id, "org_id": org_id, "nonce": str(uuid.uuid4()), "exp": exp}
    return jwt.encode(payload, secret, algorithm="HS256")

async def test_rate_limit_kicks_in(client):
    # Create an event so WRONG_EVENT isn't triggered; use invalid token to avoid redeeming tickets.
    event_id = (await client.post("/admin/events", json={"name": "RateLimit Event", "ticket_count": 1, "org_id": "org_1"})).json()["event_id"]

    hits = []
    for _ in range(12):
        r = await client.post("/validate", json={"qr_token": "definitely-not-a-jwt", "event_id": event_id})
        hits.append(r.json())

    # After 10 quick calls, at least one should be RATE_LIMITED
    assert any(x.get("reason_code") == "RATE_LIMITED" for x in hits)

async def test_idempotency_returns_same_cached_response(client):
    # This tests your idempotency cache behavior on /validate
    secret = os.environ.get("TICKET_SIGNING_SECRET", "dev_secret_change_me")

    event_id = (await client.post("/admin/events", json={"name": "Idem Event", "ticket_count": 2, "org_id": "org_1"})).json()["event_id"]
    tickets = (await client.get(f"/admin/events/{event_id}/tickets", params={"limit": 10})).json()
    ticket_id = tickets[0]["ticket_id"]

    token = mint_token(secret, ticket_id, event_id)

    key = "idem-demo-123"
    r1 = await client.post("/validate", json={"qr_token": token, "event_id": event_id}, headers={"Idempotency-Key": key})
    r2 = await client.post("/validate", json={"qr_token": token, "event_id": event_id}, headers={"Idempotency-Key": key})

    j1, j2 = r1.json(), r2.json()
    assert j1 == j2, f"Expected exact cached response, got diff: {j1} vs {j2}"
