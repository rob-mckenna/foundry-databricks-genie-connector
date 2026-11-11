#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="${ENV_FILE:-${repo_root}/.env}"
export PYTHONPATH="${repo_root}/src"
if [[ "${1:-}" == "--bootstrap" ]]; then
  shift
  python -m foundry_databricks_genie.cli bootstrap \
    --env-file "${env_file}" \
    --output "${repo_root}/.generated/toolbox.yaml" \
    "$@"
  exit $?
fi
arguments=()
if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--replace-connection" ) ]]; then
  echo "Usage: $0 [--replace-connection] | --bootstrap [bootstrap options]" >&2
  exit 2
fi
if [[ $# -eq 1 ]]; then
  arguments+=("--replace-connection")
fi

python -m foundry_databricks_genie.cli setup \
  --env-file "${env_file}" \
  --output "${repo_root}/.generated/toolbox.yaml" \
  "${arguments[@]}"
