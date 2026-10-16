#!/usr/bin/env bash
# Simple HTTP load against the read-heavy front-desk endpoints (for HPA / Grafana demos).
#   BASE=http://localhost:8000 ./scripts/load-test.sh                 # docker compose
#   BASE=http://clinicflow.local:8080 REQUESTS=2000 ./scripts/load-test.sh   # ingress (minikube tunnel / port-forward)
set -euo pipefail
BASE="${BASE:-http://localhost:8000}"
REQUESTS="${REQUESTS:-500}"
PARALLEL="${PARALLEL:-8}"
DAY="$(date +%F)"

echo "→ $REQUESTS requests to $BASE ($PARALLEL in parallel)"
seq 1 "$REQUESTS" | xargs -P "$PARALLEL" -I{} sh -c '
  case $(({} % 3)) in
    0) path="/api/appointments/stats?date='"$DAY"'" ;;
    1) path="/api/appointments?date='"$DAY"'" ;;
    *) path="/api/doctors" ;;
  esac
  curl -s -o /dev/null -w "%{http_code}\n" "'"$BASE"'$path"' | sort | uniq -c | sed 's/^/   HTTP /'
echo "Load test completed"
