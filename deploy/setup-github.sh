#!/bin/bash
# Repozytorium, środowiska test/production i ODRĘBNE sekrety dla każdego środowiska.
#   bash deploy/setup-github.sh
set -euo pipefail
cd "$(dirname "$0")/.."
REPO=lab11-srodowiska
OWNER=$(gh api user -q .login); USER_ID=$(gh api user -q .id)
rnd() { LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c "$1"; }

git init -q -b main && git add . && git commit -q -m "Lab 11: wydzielenie srodowiska produkcyjnego od testowego"
gh repo create "$REPO" --public --source . --remote origin --description "Lab 11 DevOps - separacja srodowisk test/prod"

gh api -X PUT "repos/$OWNER/$REPO/environments/test" >/dev/null
gh api -X PUT "repos/$OWNER/$REPO/environments/production" --input - >/dev/null <<JSON
{"reviewers":[{"type":"User","id":$USER_ID}],
 "deployment_branch_policy":{"protected_branches":false,"custom_branch_policies":true}}
JSON
gh api -X POST "repos/$OWNER/$REPO/environments/production/deployment-branch-policies" -f name=main >/dev/null

# Różne hasła do baz i różne klucze API - wartości nie są nigdzie wyświetlane ani zapisywane w repozytorium
gh secret set DB_PASSWORD     -R "$OWNER/$REPO" --env test       --body "$(rnd 24)"
gh secret set PAYMENT_API_KEY -R "$OWNER/$REPO" --env test       --body "sk_test_$(rnd 20)"
gh secret set DB_PASSWORD     -R "$OWNER/$REPO" --env production --body "$(rnd 24)"
gh secret set PAYMENT_API_KEY -R "$OWNER/$REPO" --env production --body "sk_live_$(rnd 20)"

for E in test production; do
  echo "== Środowisko $E, sekrety: $(gh secret list -R "$OWNER/$REPO" --env $E --json name -q '[.[].name] | join(", ")')"
done
gh api "repos/$OWNER/$REPO/environments" -q '.environments[] | "\(.name): \(.protection_rules | map(.type) | join(", "))"'
echo "Repozytorium: https://github.com/$OWNER/$REPO"
