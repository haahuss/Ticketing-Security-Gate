for i in {1..60}; do
  r=$(curl -s http://localhost:8000/validate -H "Content-Type: application/json" -d '{"qr_token":"bad","event_id":"evt_123"}' | jq -r .reason_code)
  echo "$i $r"
done
