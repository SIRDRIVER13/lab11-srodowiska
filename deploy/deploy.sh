#!/bin/bash
# Wdrożenie na wybrane środowisko z kontem ograniczonym do jego przestrzeni nazw.
#   DB_PASSWORD=... PAYMENT_API_KEY=... bash deploy/deploy.sh <test|prod> <obraz>
# Opcjonalnie: GHCR_TOKEN/GHCR_USER, SIMULATE_FAILURE=1, COMMIT=<sha>.  Zgodny z bash 3.2 (macOS).
set -uo pipefail
cd "$(dirname "$0")/.."
ENV_NAME="${1:?Podaj środowisko: test lub prod}"
IMAGE="${2:?Podaj obraz}"
case "$ENV_NAME" in
  test) NS=test; PORT=30111 ;;
  prod) NS=prod; PORT=30211 ;;
  *) echo "Nieznane środowisko $ENV_NAME"; exit 2 ;;
esac
: "${DB_PASSWORD:?Brak DB_PASSWORD (sekret środowiska)}"
: "${PAYMENT_API_KEY:?Brak PAYMENT_API_KEY (sekret środowiska)}"
# Każde polecenie wykonywane jako konto deployer TEGO środowiska (RBAC)
K="kubectl --context kind-lab11 --as=system:serviceaccount:$NS:deployer -n $NS"
SUMMARY="${GITHUB_STEP_SUMMARY:-/dev/null}"
BROKEN=""; [ "${SIMULATE_FAILURE:-0}" = "1" ] && BROKEN="1"
START=$(date +%s)
log() { echo "[$(date +%H:%M:%S)] [$NS] $*"; }

# 1. Sekrety środowiska (nie są przechowywane w repozytorium)
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
umask 077
printf 'DB_PASSWORD=%s\nPAYMENT_API_KEY=%s\n' "$DB_PASSWORD" "$PAYMENT_API_KEY" > "$TMP/secrets.env"
$K create secret generic taskapi-secrets --from-env-file="$TMP/secrets.env" --dry-run=client -o yaml | $K apply -f - >/dev/null || exit 1
if [ -n "${GHCR_TOKEN:-}" ]; then
  $K create secret docker-registry ghcr --docker-server=ghcr.io --docker-username="${GHCR_USER:-ci}" \
    --docker-password="$GHCR_TOKEN" --dry-run=client -o yaml | $K apply -f - >/dev/null
  $K patch serviceaccount default -p '{"imagePullSecrets":[{"name":"ghcr"}]}' >/dev/null
fi
log "Sekrety środowiska zapisane (taskapi-secrets)"

# 2. Konfiguracja środowiska (kustomize overlay) + obraz
kubectl kustomize "k8s/overlays/$ENV_NAME" \
  | sed -e "s|__IMAGE__|$IMAGE|g" -e "s|__BROKEN__|$BROKEN|g" -e "s|__COMMIT__|${COMMIT:-manual}|g" \
  | $K apply -f - || exit 1

# 3. Oczekiwanie na bazę, monitoring i aplikację
$K rollout status statefulset/postgres --timeout=180s || exit 1
$K rollout status deployment/prometheus --timeout=180s || log "UWAGA: Prometheus jeszcze nie gotowy"
FAILED=0
$K rollout status deployment/taskapi --timeout=150s || FAILED=1
if [ "$FAILED" = "0" ]; then
  for i in 1 2 3 4 5 6 7 8 9 10; do
    curl -fsS -m 3 "http://localhost:$PORT/health" >/dev/null 2>&1 && break
    [ "$i" = "10" ] && FAILED=1; sleep 2
  done
fi

# 4. Automatyczny rollback
if [ "$FAILED" = "1" ]; then
  log "BŁĄD WDROŻENIA - AUTOMATYCZNY ROLLBACK"
  if [ "$($K rollout history deployment/taskapi | grep -c '^[0-9]')" -gt 1 ]; then
    $K rollout undo deployment/taskapi && $K rollout status deployment/taskapi --timeout=120s
  fi
  { echo "### ❌ Wdrożenie na $NS nieudane - wykonano rollback"; echo '```'
    $K get deploy,pods -o wide; echo '```'; } >> "$SUMMARY"
  exit 1
fi

# 5. Monitoring wdrożenia
DURATION=$(( $(date +%s) - START )); OK=0
for i in $(seq 1 20); do curl -fsS -m 3 -o /dev/null "http://localhost:$PORT/health" && OK=$((OK+1)); done
log "WDROŻENIE OK w ${DURATION}s, dostępność $OK/20"
CFG=$(curl -s "http://localhost:$PORT/config")
echo "$CFG"
{ echo "### ✅ Wdrożenie: $NS"
  echo "| Parametr | Wartość |"; echo "| --- | --- |"
  echo "| Obraz | \`$IMAGE\` |"; echo "| Czas | ${DURATION} s |"; echo "| Dostępność | $OK/20 |"
  echo "| Aplikacja | http://localhost:$PORT |"; echo "| Prometheus | http://localhost:$((PORT+8)) |"
  echo '```json'; echo "$CFG"; echo '```'; } >> "$SUMMARY"
