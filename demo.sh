#!/usr/bin/env bash
# ECO-VPP end-to-end demo. Run after `docker compose up --build -d` to verify
# every service end-to-end, exercise the post-audit auth (PR #5), and show the
# price-forecast / dashboard data paths.
#
#   bash demo.sh                          # runs against localhost defaults
#   BASE=http://host:8000 bash demo.sh    # custom host
#
set -u  # don't -e: we WANT step 2 (the auth-rejection check) to keep going

TOKEN="${INGEST_TOKEN:-dev-token}"
WEBHOOK="${BASE:-http://localhost:8000}"
PRICE="${PRICE_BASE:-http://localhost:8003}"
DASH="${DASH_URL:-http://localhost:3000}"

if command -v tput >/dev/null && [ -t 1 ]; then
  R=$(tput setaf 1); G=$(tput setaf 2); Y=$(tput setaf 3); B=$(tput setaf 4); D=$(tput sgr0)
else
  R=""; G=""; Y=""; B=""; D=""
fi
say() { printf '\n%s== %s ==%s\n' "$B" "$1" "$D"; }
ok()  { printf '%s✓%s %s\n' "$G" "$D" "$1"; }
bad() { printf '%s✗%s %s\n' "$R" "$D" "$1"; }
note(){ printf '%s•%s %s\n' "$Y" "$D" "$1"; }

pretty() { if command -v jq >/dev/null; then jq .; else python3 -m json.tool 2>/dev/null || cat; fi; }

wait_for() {
  local name="$1" url="$2" t=0
  until curl -fs -o /dev/null "$url"; do
    t=$((t+2)); [ "$t" -ge 60 ] && bad "$name not ready after 60s" && return 1
    sleep 2
  done
  ok "$name ready ($url)"
}

say "0. Wait for services"
wait_for "webhook-receiver" "$WEBHOOK/healthz"
wait_for "price-forecast"   "$PRICE/healthz"

say "1. Price forecast — current point"
curl -s "$PRICE/api/v1/price/current" | pretty

say "2. H1 security check — POST /api/shares WITHOUT token must be 401"
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$WEBHOOK/api/shares?asset=apt-1&kwh=1&price=0.2")
if [ "$code" = "401" ]; then ok "no-token POST /api/shares -> 401 (auth working)"
else bad "expected 401, got $code (auth NOT enforced!)"; fi

say "3. Register an apartment meter (token required)"
curl -s -X POST "$WEBHOOK/api/v1/assets" \
  -H "Content-Type: application/json" -H "X-Ingest-Token: $TOKEN" \
  -d '{"did":"did:ethr:volta:0x111","asset_type":"meter","location":"Apt 1","capacity_kw":3.5}' \
  | pretty

say "4. Ingest a telemetry sample"
curl -s -X POST "$WEBHOOK/api/v1/telemetry/ingest" \
  -H "Content-Type: application/json" -H "X-Ingest-Token: $TOKEN" \
  -d '{"did":"did:ethr:volta:0x111","voltage":230.1,"current":1.42,"power_w":326.7,"energy_kwh":0.054,"confidence":0.96}' \
  | pretty

say "5. Create an on-chain-settled share (with token)"
curl -s -X POST "$WEBHOOK/api/shares?asset=did:ethr:volta:0x111&kwh=2.5&price=0.18" \
  -H "X-Ingest-Token: $TOKEN" | pretty

say "6. Latest shares (last 24h)"
curl -s "$WEBHOOK/api/shares/latest" | pretty | head -40

say "7. Flexibility-engine metrics (price + signal updating every few seconds)"
curl -s http://localhost:8001/metrics 2>/dev/null \
  | grep -E '^(ecovpp_grid_price|ecovpp_grid_signal|ecovpp_load_commands_total) ' \
  || note "(flexibility-engine metrics endpoint not reachable — check it's running)"

say "DONE"
note "Dashboard: $DASH"
note "Tear down: docker compose down -v"
