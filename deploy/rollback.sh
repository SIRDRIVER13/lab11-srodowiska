#!/bin/bash
# Ręczny rollback aplikacji na wybranym środowisku:  bash deploy/rollback.sh <test|prod>
set -euo pipefail
NS="${1:?Podaj środowisko: test lub prod}"
K="kubectl --context kind-lab11 --as=system:serviceaccount:$NS:deployer -n $NS"
echo "Przed: $($K get deploy/taskapi -o jsonpath='{.spec.template.spec.containers[0].image}')"
$K rollout undo deployment/taskapi
$K rollout status deployment/taskapi --timeout=120s
echo "Po:    $($K get deploy/taskapi -o jsonpath='{.spec.template.spec.containers[0].image}')"
$K rollout history deployment/taskapi
