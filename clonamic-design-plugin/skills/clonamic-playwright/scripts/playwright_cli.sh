#!/usr/bin/env bash
set -euo pipefail

if command -v playwright-cli >/dev/null 2>&1; then
  runtime=("$(command -v playwright-cli)")
elif [[ -x "./node_modules/.bin/playwright-cli" ]]; then
  runtime=("./node_modules/.bin/playwright-cli")
else
  echo "Error: playwright-cli is not already installed on PATH or in ./node_modules/.bin." >&2
  echo "Installation is a separate setup action; this wrapper never downloads packages." >&2
  exit 1
fi

has_session_flag="false"
for arg in "$@"; do
  case "$arg" in
    --session|--session=*)
      has_session_flag="true"
      break
      ;;
  esac
done

cmd=("${runtime[@]}")
if [[ "${has_session_flag}" != "true" && -n "${PLAYWRIGHT_CLI_SESSION:-}" ]]; then
  cmd+=(--session "${PLAYWRIGHT_CLI_SESSION}")
fi
cmd+=("$@")

exec "${cmd[@]}"
