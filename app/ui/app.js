async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts
  });
  return res.json();
}

function setJson(id, obj) {
  document.getElementById(id).textContent = JSON.stringify(obj, null, 2);
}

async function refreshOfflineBadge() {
  const data = await api("/admin/offline");
  document.getElementById("offlineBadge").textContent = `Offline: ${data.offline}`;
}

async function toggleOffline(enabled) {
  const data = await api("/admin/offline", { method: "POST", body: JSON.stringify({ enabled }) });
  await refreshOfflineBadge();
  return data;
}

async function createEvent() {
  const event_id = document.getElementById("eventId").value.trim();
  const org_id = document.getElementById("orgId").value.trim();
  const out = await api("/admin/events", { method: "POST", body: JSON.stringify({ event_id, org_id }) });
  setJson("eventOut", out);
}

async function createTicket() {
  const ticket_id = document.getElementById("ticketId").value.trim();
  const event_id = document.getElementById("ticketEventId").value.trim();
  const org_id = document.getElementById("orgId").value.trim();
  const out = await api("/admin/tickets", { method: "POST", body: JSON.stringify({ ticket_id, event_id, org_id }) });
  setJson("tokenOut", out);
  await refreshAudit();
}

async function mintToken() {
  const ticket_id = document.getElementById("ticketId").value.trim();
  const event_id = document.getElementById("ticketEventId").value.trim();
  const org_id = document.getElementById("orgId").value.trim();
  const out = await api("/admin/mint", { method: "POST", body: JSON.stringify({ ticket_id, event_id, org_id, ttl_minutes: 60 }) });
  setJson("tokenOut", out);
  document.getElementById("qrToken").value = out.token;
}

async function validateTicket() {
  const qr_token = document.getElementById("qrToken").value.trim();
  const event_id = document.getElementById("validateEventId").value.trim();
  const idem = document.getElementById("idemKey").value.trim();

  const headers = {};
  if (idem) headers["Idempotency-Key"] = idem;

  const out = await api("/validate", { method: "POST", headers, body: JSON.stringify({ qr_token, event_id }) });
  setJson("validateOut", out);
  await refreshAudit();
}

async function refreshAudit() {
  const rows = await api("/admin/audit?limit=25");
  const body = document.getElementById("auditBody");
  body.innerHTML = "";
  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${r.created_at}</td>
      <td>${r.ticket_id || ""}</td>
      <td>${r.status}</td>
      <td>${r.reason_code}</td>
      <td style="font-family: ui-monospace, SFMono-Regular; font-size: 11px;">${r.decision_id}</td>
    `;
    body.appendChild(tr);
  }
}

window.toggleOffline = toggleOffline;
window.createEvent = createEvent;
window.createTicket = createTicket;
window.mintToken = mintToken;
window.validateTicket = validateTicket;
window.refreshAudit = refreshAudit;

refreshOfflineBadge();
refreshAudit();
