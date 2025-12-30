TOKEN=$(python scripts/mint_token.py --ticket-id tkt_abc --event-id evt_123 --org-id org_1)

curl -s http://localhost:8000/validate \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: demo-1" \
  -d "{\"qr_token\":\"$TOKEN\",\"event_id\":\"evt_123\"}"

# {"status":"ACCEPTED","reason_code":"OK","ticket_id":"tkt_abc","decision_id":"ec01c21f-7892-43e6-aa06-773587d7b6f5"}