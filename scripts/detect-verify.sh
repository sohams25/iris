#!/usr/bin/env bash
# Detect the appropriate verification command for the current repo.
# Prints the command to stdout. Caller runs `bash -c "$(detect-verify.sh)"`.
#
# Detection precedence (first match wins):
#   1. VERIFY_CMD env var (explicit override)
#   2. scripts/verify.sh in repo root
#   3. pnpm-lock.yaml      -> pnpm test+typecheck+build
#   4. yarn.lock           -> yarn test+typecheck+build
#   5. package-lock.json   -> npm ci + test + typecheck + build
#   6. Cargo.toml          -> cargo test + cargo clippy
#   7. pyproject.toml      -> ruff + pytest
#   8. go.mod              -> go test ./... + go vet ./...
#   9. fallback            -> echo + exit 0 (no verify configured)
set -euo pipefail

ROOT="${1:-$(pwd)}"
cd "$ROOT"

if [[ -n "${VERIFY_CMD:-}" ]]; then
  echo "$VERIFY_CMD"
  exit 0
fi

if [[ -x scripts/verify.sh ]]; then
  echo "bash scripts/verify.sh"
  exit 0
fi

if [[ -f pnpm-lock.yaml ]]; then
  cmd="pnpm install --frozen-lockfile"
  [[ -f package.json ]] && grep -q '"test"' package.json && cmd="$cmd && pnpm test"
  [[ -f package.json ]] && grep -q '"typecheck"' package.json && cmd="$cmd && pnpm typecheck"
  [[ -f package.json ]] && grep -q '"build"' package.json && cmd="$cmd && pnpm build"
  echo "$cmd"
  exit 0
fi

if [[ -f yarn.lock ]]; then
  cmd="yarn install --frozen-lockfile"
  [[ -f package.json ]] && grep -q '"test"' package.json && cmd="$cmd && yarn test"
  [[ -f package.json ]] && grep -q '"typecheck"' package.json && cmd="$cmd && yarn typecheck"
  [[ -f package.json ]] && grep -q '"build"' package.json && cmd="$cmd && yarn build"
  echo "$cmd"
  exit 0
fi

if [[ -f package-lock.json ]]; then
  cmd="npm ci"
  [[ -f package.json ]] && grep -q '"test"' package.json && cmd="$cmd && npm test"
  [[ -f package.json ]] && grep -q '"typecheck"' package.json && cmd="$cmd && npm run typecheck"
  [[ -f package.json ]] && grep -q '"build"' package.json && cmd="$cmd && npm run build"
  echo "$cmd"
  exit 0
fi

if [[ -f Cargo.toml ]]; then
  echo "cargo test && cargo clippy --all-targets -- -D warnings"
  exit 0
fi

if [[ -f pyproject.toml ]]; then
  cmd=""
  command -v ruff >/dev/null 2>&1 && cmd="ruff check ."
  if command -v pytest >/dev/null 2>&1; then
    [[ -n "$cmd" ]] && cmd="$cmd && pytest" || cmd="pytest"
  fi
  [[ -z "$cmd" ]] && cmd="echo 'no python verify tools installed' && exit 0"
  echo "$cmd"
  exit 0
fi

if [[ -f go.mod ]]; then
  echo "go test ./... && go vet ./..."
  exit 0
fi

echo "echo 'no verify command configured (set VERIFY_CMD or add scripts/verify.sh)' && exit 0"
