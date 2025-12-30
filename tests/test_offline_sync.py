import asyncio
import pytest
from tests.helpers import create_event, list_tickets

pytestmark = pytest.mark.asyncio

async def test_offline_pending_then_replay_on_sync(client):
    event_id = await create_event(client, name="Offline Sync Event", ticket_count=5)
    tickets = await list_tickets(client, event_id)
    ticket_id = tickets[0]["ticket_id"]

    # First redeem online
    r1 = (await client.post("/admin/scan", json={"event_id": event_id, "ticket_id": ticket_id, "org_id": "org_1"})).json()
    assert r1["status"] == "ACCEPTED"

    # Go offline
    await client.post("/admin/offline", json={"enabled": True})

    # Scan same redeemed ticket while offline -> pending
    r2 = (await client.post("/admin/scan", json={"event_id": event_id, "ticket_id": ticket_id, "org_id": "org_1"})).json()
    assert r2["status"] == "PENDING_SYNC"
    pending_decision = r2["decision_id"]

    # Go online so worker drains queue
    await client.post("/admin/offline", json={"enabled": False})

    # Poll audit logs until we see REPLAY_ON_SYNC for this ticket OR decision
    for _ in range(30):
        logs = (await client.get("/admin/audit", params={"limit": 200})).json()
        # look for sync result for the pending decision or ticket
        found = [x for x in logs if (x.get("decision_id") == pending_decision and x.get("reason_code") in ("OK_SYNCED", "REPLAY_ON_SYNC"))]
        if found:
            # Because ticket was already redeemed earlier, the sync result should be replay
            assert found[0]["reason_code"] == "REPLAY_ON_SYNC"
            return
        await asyncio.sleep(1.0)

    assert False, "Did not observe sync result audit log after returning online"
