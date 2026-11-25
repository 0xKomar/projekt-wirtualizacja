#!/usr/bin/env bash
# Walks through every API endpoint with curl and checks the HTTP codes.
# Usage: demo/api.sh [base URL]    default: http://localhost:8080 (through the frontend, like the ESP)
set -eu

BASE=${1:-http://localhost:8080}
BASE=${BASE%/}
FAILED=0

# step "title" expected_code curl_args...
# Prints the request and the answer, keeps the answer body in $BODY.
step() {
    local title=$1 expected=$2
    shift 2
    echo
    echo "== $title"
    # Show the command ready to copy: arguments with spaces or "?" in quotes.
    local cmd="curl" arg out code
    for arg in "$@"; do
        case $arg in
            *" "* | *"?"*) cmd+=" '$arg'" ;;
            *) cmd+=" $arg" ;;
        esac
    done
    echo "$cmd"
    out=$(curl -sS -w '\n%{http_code}' "$@")
    code=${out##*$'\n'}
    BODY=${out%$'\n'*}
    echo "-> HTTP $code"
    echo "$BODY"
    if [ "$code" != "$expected" ]; then
        echo "!! expected HTTP $expected"
        FAILED=1
    fi
}

JSON="Content-Type: application/json"
READING='{"db_avg": 58.2, "db_min": 51.0, "db_max": 66.4}'

# Takes "id" from the last answer.
last_id() {
    echo "$BODY" | sed -n 's/^{"id":\([0-9]*\).*/\1/p'
}

echo "API demo against $BASE"

step "Health: backend and database" 200 \
    "$BASE/api/health"

# Locations
step "Add a location" 201 \
    -X POST -H "$JSON" -d '{"name": "Demo: Plac Wolnosci", "lat": 52.4085, "lon": 16.9307}' \
    "$BASE/api/locations"
LOCATION_ID=$(last_id)

step "All locations" 200 \
    "$BASE/api/locations"

step "One location" 200 \
    "$BASE/api/locations/$LOCATION_ID"

step "Change a location" 200 \
    -X PUT -H "$JSON" -d '{"name": "Demo: Plac Wolnosci (fountain)", "lat": 52.4086, "lon": 16.9305}' \
    "$BASE/api/locations/$LOCATION_ID"

# Devices
step "Add a device (the key is shown only once)" 201 \
    -X POST -H "$JSON" -d "{\"name\": \"Demo sensor $(date +%H%M%S)\", \"location_id\": $LOCATION_ID}" \
    "$BASE/api/devices"
DEVICE_ID=$(last_id)
KEY=$(echo "$BODY" | sed -n 's/.*"key":"\([^"]*\)".*/\1/p')

step "Rename the device (the key stays the same)" 200 \
    -X PUT -H "$JSON" -d "{\"name\": \"Demo sensor $DEVICE_ID\", \"location_id\": $LOCATION_ID}" \
    "$BASE/api/devices/$DEVICE_ID"

# Readings
step "Send a reading with the device key" 201 \
    -X POST -H "$JSON" -H "X-Device-Key: $KEY" -d "$READING" \
    "$BASE/api/readings"

step "Wrong key is rejected" 401 \
    -X POST -H "$JSON" -H "X-Device-Key: wrong-key" -d "$READING" \
    "$BASE/api/readings"

step "Bad data is rejected (db_min above db_avg)" 400 \
    -X POST -H "$JSON" -H "X-Device-Key: $KEY" -d '{"db_avg": 50.0, "db_min": 60.0, "db_max": 70.0}' \
    "$BASE/api/readings"

step "All devices with the last reading" 200 \
    "$BASE/api/devices"

step "One device" 200 \
    "$BASE/api/devices/$DEVICE_ID"

step "Reading history of the device (newest first)" 200 \
    "$BASE/api/devices/$DEVICE_ID/readings?limit=5"

step "Unknown device" 404 \
    "$BASE/api/devices/999999"

# Deleting
step "A device with readings cannot be deleted" 409 \
    -X DELETE "$BASE/api/devices/$DEVICE_ID"

step "A location with devices cannot be deleted" 409 \
    -X DELETE "$BASE/api/locations/$LOCATION_ID"

step "Add a location that nothing uses" 201 \
    -X POST -H "$JSON" -d '{"name": "Demo: to delete", "lat": 52.4, "lon": 16.9}' \
    "$BASE/api/locations"

step "Delete it" 204 \
    -X DELETE "$BASE/api/locations/$(last_id)"

echo
if [ "$FAILED" -ne 0 ]; then
    echo "Some steps returned an unexpected HTTP code."
    exit 1
fi
echo "All steps returned the expected HTTP code."
