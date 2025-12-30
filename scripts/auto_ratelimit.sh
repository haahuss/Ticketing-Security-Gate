for i in {1..80}; do
  curl -s http://localhost:8000/validate \
    -H "Content-Type: application/json" \
    -d '{"qr_token":"bad","event_id":"evt_123"}' \
  | jq -r '.reason_code'
done | sort | uniq -c
