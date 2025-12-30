import asyncio
import pytest
from tests.helpers import create_event, list_tickets

pytestmark = pytest.mark.asyncio

async def test_replay_basic(client):
    event_id = await create_event(client, name="Replay Event", ticket_count=5)
    tickets = await list_tickets(client, event_id)
    ticket_id = tickets[0]["ticket_id"]

    r1 = (await client.post("/admin/scan", json={"event_id": event_id, "ticket_id": ticket_id, "org_id": "org_1"})).json()
    assert r1["status"] in ("ACCEPTED", "PENDING_SYNC")  # should be ACCEPTED because offline=false in fixture

    r2 = (await client.post("/admin/scan", json={"event_id": event_id, "ticket_id": ticket_id, "org_id": "org_1"})).json()
    assert r2["status"] == "REJECTED"
    assert r2["reason_code"] in ("REPLAY", "REPLAY_ON_SYNC")

async def test_concurrent_scan_one_wins(client):
    event_id = await create_event(client, name="Concurrency Event", ticket_count=5)
    tickets = await list_tickets(client, event_id)
    ticket_id = tickets[0]["ticket_id"]

    async def one():
        return (await client.post("/admin/scan", json={"event_id": event_id, "ticket_id": ticket_id, "org_id": "org_1"})).json()

    results = await asyncio.gather(*[one() for _ in range(20)])
    accepted = [x for x in results if x.get("status") == "ACCEPTED"]
    rejected = [x for x in results if x.get("status") == "REJECTED"]

    assert len(accepted) == 1, f"Expected exactly 1 ACCEPTED, got {len(accepted)}"
    assert len(rejected) >= 19
    assert all(r.get("reason_code") in ("REPLAY", "REPLAY_ON_SYNC") for r in rejected)
