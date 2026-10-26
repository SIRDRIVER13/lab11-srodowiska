#!/bin/bash
# Self-hosted runner dla repozytorium lab11 (wdraża do lokalnego klastra kind lab11)
set -euo pipefail
REPO=lab11-srodowiska
OWNER=$(gh api user -q .login)
VER=$(gh api repos/actions/runner/releases/latest -q .tag_name | sed 's/^v//')
ARCH=$([ "$(uname -m)" = arm64 ] && echo arm64 || echo x64)
DIR="$HOME/actions-runner-lab11"
mkdir -p "$DIR" && cd "$DIR"
curl -fsSL -o runner.tar.gz "https://github.com/actions/runner/releases/download/v$VER/actions-runner-osx-$ARCH-$VER.tar.gz"
tar xzf runner.tar.gz && rm runner.tar.gz
TOKEN=$(gh api -X POST "repos/$OWNER/$REPO/actions/runners/registration-token" -q .token)
./config.sh --url "https://github.com/$OWNER/$REPO" --token "$TOKEN" --name mac-lab11 --labels lab11 --unattended --replace
echo "Gotowe. Uruchom w osobnej karcie:  cd $DIR && ./run.sh"
