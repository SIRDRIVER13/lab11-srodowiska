#!/bin/bash
# Weryfikacja separacji środowisk test i prod (uruchamiać z uprawnieniami administratora klastra)
TEST=http://localhost:30111; PROD=http://localhost:30211
K="kubectl --context kind-lab11"
step() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

step "1. Konfiguracja wczytana przez aplikację (ConfigMap + Secret)"
echo "--- TEST";  curl -s $TEST/config
echo "--- PROD";  curl -s $PROD/config

step "2. Dane: zadanie zapisane na TEST nie pojawia się na PROD"
TITLE="separacja-$(date +%H%M%S)"
curl -s -X POST $TEST/tasks -H 'Content-Type: application/json' -d "{\"title\":\"$TITLE\"}"; echo
printf 'TEST - liczba zadań "%s": ' "$TITLE"; curl -s $TEST/tasks | grep -o "$TITLE" | wc -l
printf 'PROD - liczba zadań "%s": ' "$TITLE"; curl -s $PROD/tasks | grep -o "$TITLE" | wc -l
$K -n test exec statefulset/postgres -- sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select current_database(), count(*) from tasks"'
$K -n prod exec statefulset/postgres -- sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select current_database(), count(*) from tasks"'

step "3. Usługa zewnętrzna: TEST -> sandbox, klucz testowy odrzucany przez usługę LIVE"
curl -s -X POST $TEST/pay; echo
$K -n test exec deploy/taskapi -- python -c "
import os, requests
r = requests.post('http://payments-live.external.svc.cluster.local:8080/charge', json={'amount': 1},
                  headers={'X-Api-Key': os.environ['PAYMENT_API_KEY']}, timeout=3)
print('klucz TEST -> usluga LIVE:', r.status_code, r.json())"

step "4. Sieć: aplikacja TEST nie może połączyć się z bazą PROD (NetworkPolicy)"
$K -n test exec deploy/taskapi -- python -c "
import socket
for host in ['postgres.test.svc.cluster.local', 'postgres.prod.svc.cluster.local']:
    try:
        socket.create_connection((host, 5432), timeout=3).close(); print(host, '-> POLACZENIE OK')
    except OSError as e:
        print(host, '-> ZABLOKOWANE (', type(e).__name__, ')')"

step "5. Uprawnienia: konto wdrożeniowe TEST nie ma dostępu do PROD (RBAC)"
for NS in test prod; do
  printf 'deployer z test -> deployments w %-4s: ' $NS
  $K auth can-i update deployments -n $NS --as=system:serviceaccount:test:deployer
done
printf 'deployer z test -> secrets w prod     : '; $K auth can-i get secrets -n prod --as=system:serviceaccount:test:deployer
