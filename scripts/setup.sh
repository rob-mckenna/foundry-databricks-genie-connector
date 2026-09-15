#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="${ENV_FILE:-${repo_root}/.env}"
replace_connection=false

if [[ "${1:-}" == "--replace-connection" ]]; then
  replace_connection=true
elif [[ -n "${1:-}" ]]; then
  echo "Usage: $0 [--replace-connection]" >&2
  exit 2
fi

export PYTHONPATH="${repo_root}/src"

python -m foundry_databricks_genie.cli preflight
python -m foundry_databricks_genie.cli validate --env-file "${env_file}"

config_json="$(
  python -m foundry_databricks_genie.cli config --env-file "${env_file}"
)"

get_config() {
  local key="$1"
  python -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]])' \
    "${key}" <<<"${config_json}"
}

project_endpoint="$(get_config foundry_project_endpoint)"
connection_name="$(get_config foundry_connection_name)"
toolbox_name="$(get_config foundry_toolbox_name)"
genie_mcp_endpoint="$(get_config genie_mcp_endpoint)"

generated_directory="${repo_root}/.generated"
toolbox_file="${generated_directory}/toolbox.yaml"
python -m foundry_databricks_genie.cli render-toolbox \
  --env-file "${env_file}" \
  --output "${toolbox_file}"

connection_state_file="${generated_directory}/connection.json"
if azd ai connection show "${connection_name}" \
  --project-endpoint "${project_endpoint}" \
  --output json \
  --no-prompt >"${connection_state_file}" 2>/dev/null; then
  if [[ "${replace_connection}" == true ]]; then
    azd ai connection create "${connection_name}" \
      --kind remote-tool \
      --target "${genie_mcp_endpoint}" \
      --auth-type oauth2 \
      --connector-name foundrydatabricksmcp \
      --project-endpoint "${project_endpoint}" \
      --output json \
      --no-prompt \
      --force
  else
    python -m foundry_databricks_genie.cli assert-connection \
      --input "${connection_state_file}" \
      --expected-name "${connection_name}" \
      --expected-target "${genie_mcp_endpoint}"
  fi
else
  azd ai connection create "${connection_name}" \
    --kind remote-tool \
    --target "${genie_mcp_endpoint}" \
    --auth-type oauth2 \
    --connector-name foundrydatabricksmcp \
    --project-endpoint "${project_endpoint}" \
    --output json \
    --no-prompt
fi

if azd ai toolbox show "${toolbox_name}" \
  --project-endpoint "${project_endpoint}" \
  --output json \
  --no-prompt >/dev/null 2>&1; then
  toolbox_state_file="${generated_directory}/toolbox-connections.json"
  azd ai toolbox connection list "${toolbox_name}" \
    --project-endpoint "${project_endpoint}" \
    --output json \
    --no-prompt >"${toolbox_state_file}"
  python -m foundry_databricks_genie.cli assert-toolbox-connections \
    --input "${toolbox_state_file}" \
    --expected-name "${connection_name}"
else
  azd ai toolbox create "${toolbox_name}" \
    --from-file "${toolbox_file}" \
    --project-endpoint "${project_endpoint}" \
    --output json \
    --no-prompt
fi

cat <<EOF

Setup completed.
Connection: ${connection_name}
Toolbox:    ${toolbox_name}

Next: attach the Toolbox to an agent, invoke Genie, and complete the
Databricks OAuth consent flow when Foundry returns CONSENT_REQUIRED.
EOF
