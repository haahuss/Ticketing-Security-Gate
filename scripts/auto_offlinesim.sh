# export TICKET_SIGNING_SECRET=dev_secret_change_me
TOKEN2=$(python3 scripts/mint_token.py --ticket-id tkt_def --event-id evt_123 --org-id org_1)

curl -s http://localhost:8000/validate \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg t "$TOKEN2" --arg e "evt_123" '{qr_token:$t,event_id:$e}')" | jq

