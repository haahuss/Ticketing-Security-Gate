import httpx

async def create_event(client: httpx.AsyncClient, name="Test Event", ticket_count=10, org_id="org_1") -> str:
    r = await client.post("/admin/events", json={"name": name, "ticket_count": ticket_count, "org_id": org_id})
    r.raise_for_status()
    data = r.json()
    assert data.get("ok") is True, data
    return data["event_id"]

async def list_tickets(client: httpx.AsyncClient, event_id: str, limit: int = 500):
    r = await client.get(f"/admin/events/{event_id}/tickets", params={"limit": limit})
    r.raise_for_status()
    data = r.json()
    assert isinstance(data, list)
    return data
