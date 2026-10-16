#!/usr/bin/env bash
# Fill ClinicFlow with a realistic front-desk day through the public REST API
# (the doctors themselves come from the Alembic seed migration 0002).
#   BASE=http://localhost:8000 ./scripts/seed-demo.sh          # docker compose
#   BASE=http://clinicflow.local:8080 RESOLVE=clinicflow.local:8080:127.0.0.1 ./scripts/seed-demo.sh
#                                                              # through the ingress (port-forward, no /etc/hosts entry)
#   DAY=2026-10-20 ./scripts/seed-demo.sh                      # another date (default: today)
set -euo pipefail
BASE="${BASE:-http://localhost:8000}"
DAY="${DAY:-$(date +%F)}"

# shellcheck disable=SC2086
curl() { command curl ${RESOLVE:+--resolve "$RESOLVE"} "$@"; }
post() { curl -fsS -X POST "$BASE$1" -H 'Content-Type: application/json' -d "$2"; }
put()  { curl -fsS -X PUT  "$BASE$1" -H 'Content-Type: application/json' -d "$2" >/dev/null; }
id_of() { python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])'; }

curl -fsS "$BASE/api/doctors" | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d else "no doctors - run the migrations first")'

echo "→ registering patients"
declare -a P
while IFS='|' read -r name phone email dob; do
  if [ -n "$email" ]; then email_json="\"$email\""; else email_json=null; fi
  id=$(post /api/patients "{\"full_name\":\"$name\",\"phone\":\"$phone\",\"email\":$email_json,\"date_of_birth\":\"$dob\"}" | id_of)
  P+=("$id")
done <<'EOF'
Riya Sharma|+91 98200 11111|riya.sharma@example.com|1994-03-12
Kabir Singh|+91 99300 22222||1987-11-02
Ananya Das|+91 98450 33333|ananya.d@example.com|2019-06-25
Vikram Rao|+91 97400 44444|vikram.rao@example.com|1961-01-30
Fatima Khan|+91 98860 55555||2001-09-18
Aditya Joshi|+91 99000 66666|aditya.j@example.com|1976-04-07
Neha Gupta|+91 98110 77777|neha.g@example.com|1990-12-21
Arnav Pillai|+91 97690 88888||2016-08-14
EOF

echo "→ booking appointments for $DAY"
# patient-index|doctor-id|time|minutes|reason|final status
declare -a A
while IFS='|' read -r p doc t mins reason status; do
  id=$(post /api/appointments "{\"patient_id\":${P[$p]},\"doctor_id\":$doc,\"scheduled_at\":\"${DAY}T$t:00\",\"duration_minutes\":$mins,\"reason\":\"$reason\"}" | id_of)
  case "$status" in
    CHECKED_IN) put "/api/appointments/$id" '{"status":"CHECKED_IN"}' ;;
    COMPLETED)  put "/api/appointments/$id" '{"status":"CHECKED_IN"}'; put "/api/appointments/$id" '{"status":"COMPLETED","notes":"Reviewed, follow-up in 4 weeks"}' ;;
    CANCELLED|NO_SHOW) put "/api/appointments/$id" "{\"status\":\"$status\"}" ;;
  esac
  A+=("$id")
done <<'EOF'
0|1|09:00|30|Fever and sore throat|COMPLETED
3|2|09:30|45|Chest pain review, ECG|COMPLETED
2|3|10:00|20|Vaccination (MMR booster)|COMPLETED
1|4|10:30|30|Knee pain after running|CHECKED_IN
4|5|11:00|20|Skin rash|CHECKED_IN
5|2|11:30|30|Blood pressure follow-up|SCHEDULED
6|1|12:00|30|Annual health check|SCHEDULED
7|3|15:00|20|Ear infection|SCHEDULED
0|5|16:00|20|Acne follow-up|CANCELLED
1|1|17:30|30|Back pain|NO_SHOW
3|4|18:00|30|Hip X-ray results|SCHEDULED
EOF

echo "→ a double booking must be rejected:"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/appointments" -H 'Content-Type: application/json' \
  -d "{\"patient_id\":${P[6]},\"doctor_id\":2,\"scheduled_at\":\"${DAY}T11:40:00\",\"reason\":\"walk-in\"}")
echo "   POST same doctor 11:40 (overlaps 11:30-12:00) -> HTTP $code"

echo "→ stats for $DAY"
curl -fsS "$BASE/api/appointments/stats?date=$DAY"; echo
