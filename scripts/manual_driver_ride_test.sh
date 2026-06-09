#!/usr/bin/env bash
# Manual end-to-end test: real driver completes a ride (MOCK_DRIVER_ENABLED=false).
# Requires: API running, DB seeded, OTP_DEBUG=true, Dev Driver KYC approved.
set -euo pipefail

BASE="${BASE_URL:-http://localhost:8000}"
API="$BASE/api/v1"

echo "=== Driver OTP ==="
DRIVER_OTP_RESP=$(curl -s -X POST "$API/driver/auth/request-otp" \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"9999000001","country_code":"+91","device_id":"manual-test","platform":"android"}')
DRIVER_OTP=$(echo "$DRIVER_OTP_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['debug_otp'])")

echo "=== Driver login ==="
DRIVER_AUTH=$(curl -s -X POST "$API/driver/auth/verify-otp" \
  -H "Content-Type: application/json" \
  -d "{\"phone_number\":\"9999000001\",\"country_code\":\"+91\",\"otp\":\"$DRIVER_OTP\",\"device_id\":\"manual-test\",\"platform\":\"android\"}")
DRIVER_TOKEN=$(echo "$DRIVER_AUTH" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "=== Driver go online ==="
curl -s -X PATCH "$API/driver/status" \
  -H "Authorization: Bearer $DRIVER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status":"online","latitude":12.9700,"longitude":77.5900}' | python3 -m json.tool

echo "=== Rider OTP ==="
RIDER_OTP_RESP=$(curl -s -X POST "$API/auth/request-otp" \
  -H "Content-Type: application/json" \
  -d '{"phone":"+919876543210"}')
RIDER_OTP=$(echo "$RIDER_OTP_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['debug_otp'])")

echo "=== Rider login ==="
RIDER_AUTH=$(curl -s -X POST "$API/auth/verify-otp" \
  -H "Content-Type: application/json" \
  -d "{\"phone\":\"+919876543210\",\"code\":\"$RIDER_OTP\",\"name\":\"Krishna\"}")
RIDER_TOKEN=$(echo "$RIDER_AUTH" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")

echo "=== Quote + book ==="
QUOTE=$(curl -s -X POST "$API/rides/quote" \
  -H "Content-Type: application/json" \
  -d '{"pickup":{"lat":"12.9716","lng":"77.5946"},"drop":{"lat":"12.9352","lng":"77.6245"}}')
PICKUP_ADDR=$(echo "$QUOTE" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['pickup_address'])")
DROP_ADDR=$(echo "$QUOTE" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['drop_address'])")

RIDE=$(curl -s -X POST "$API/rides" \
  -H "Authorization: Bearer $RIDER_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: manual-$(date +%s)" \
  -d "{\"pickup\":{\"lat\":\"12.9716\",\"lng\":\"77.5946\"},\"drop\":{\"lat\":\"12.9352\",\"lng\":\"77.6245\"},\"pickup_address\":\"$PICKUP_ADDR\",\"drop_address\":\"$DROP_ADDR\",\"ride_type_slug\":\"mini\"}")
RIDE_ID=$(echo "$RIDE" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['id'])")
echo "Ride ID: $RIDE_ID"

echo "=== Driver search ==="
curl -s "$API/driver/rides/search?lat=12.9700&lng=77.5900&radius_km=5" \
  -H "Authorization: Bearer $DRIVER_TOKEN" | python3 -m json.tool

echo "=== Accept ==="
curl -s -X POST "$API/driver/rides/$RIDE_ID/accept" \
  -H "Authorization: Bearer $DRIVER_TOKEN" | python3 -m json.tool

echo "=== Arrived ==="
ARRIVED=$(curl -s -X POST "$API/driver/rides/$RIDE_ID/arrived" \
  -H "Authorization: Bearer $DRIVER_TOKEN")
START_OTP=$(echo "$ARRIVED" | python3 -c "import sys,json; print(json.load(sys.stdin)['start_otp'])")
echo "Start OTP: $START_OTP"

echo "=== Start ==="
curl -s -X POST "$API/driver/rides/$RIDE_ID/start" \
  -H "Authorization: Bearer $DRIVER_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"otp\":\"$START_OTP\"}" | python3 -m json.tool

echo "=== Complete ==="
curl -s -X POST "$API/driver/rides/$RIDE_ID/complete" \
  -H "Authorization: Bearer $DRIVER_TOKEN" | python3 -m json.tool

echo "Done."
