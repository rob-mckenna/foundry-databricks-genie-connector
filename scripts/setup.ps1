[CmdletBinding()]
param(
    [string]$EnvFile,
    [switch]$ReplaceConnection
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $EnvFile) {
    $EnvFile = Join-Path $RepoRoot ".env"
}

$env:PYTHONPATH = Join-Path $RepoRoot "src"

function Invoke-Checked {
    param(
        [Parameter(Mandatory)]
        [scriptblock]$Command,
        [Parameter(Mandatory)]
        [string]$FailureMessage
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw $FailureMessage
    }
}

Invoke-Checked {
    python -m foundry_databricks_genie.cli preflight
} "Local prerequisite validation failed."

Invoke-Checked {
    python -m foundry_databricks_genie.cli validate --env-file $EnvFile
} "Connector configuration is invalid."

$ConfigJson = & python -m foundry_databricks_genie.cli config --env-file $EnvFile
if ($LASTEXITCODE -ne 0) {
    throw "Could not load connector configuration."
}
$Config = $ConfigJson | ConvertFrom-Json

$GeneratedDirectory = Join-Path $RepoRoot ".generated"
$ToolboxFile = Join-Path $GeneratedDirectory "toolbox.yaml"
Invoke-Checked {
    python -m foundry_databricks_genie.cli render-toolbox `
        --env-file $EnvFile `
        --output $ToolboxFile
} "Could not render the Toolbox configuration."

$ConnectionJson = & azd ai connection show `
    $Config.foundry_connection_name `
    --project-endpoint $Config.foundry_project_endpoint `
    --output json `
    --no-prompt 2>$null
$ConnectionExists = $LASTEXITCODE -eq 0

if ($ConnectionExists -and -not $ReplaceConnection) {
    $ConnectionStateFile = Join-Path $GeneratedDirectory "connection.json"
    $ConnectionJson | Set-Content -Path $ConnectionStateFile -Encoding utf8
    Invoke-Checked {
        python -m foundry_databricks_genie.cli assert-connection `
            --input $ConnectionStateFile `
            --expected-name $Config.foundry_connection_name `
            --expected-target $Config.genie_mcp_endpoint
    } "The existing connection does not match this configuration."
} else {
    $ConnectionArguments = @(
        "ai", "connection", "create", $Config.foundry_connection_name,
        "--kind", "remote-tool",
        "--target", $Config.genie_mcp_endpoint,
        "--auth-type", "oauth2",
        "--connector-name", "foundrydatabricksmcp",
        "--project-endpoint", $Config.foundry_project_endpoint,
        "--output", "json",
        "--no-prompt"
    )
    if ($ConnectionExists) {
        $ConnectionArguments += "--force"
    }
    Invoke-Checked {
        & azd @ConnectionArguments
    } "Could not create the managed OAuth project connection."
}

$null = & azd ai toolbox show `
    $Config.foundry_toolbox_name `
    --project-endpoint $Config.foundry_project_endpoint `
    --output json `
    --no-prompt 2>$null
$ToolboxExists = $LASTEXITCODE -eq 0

if ($ToolboxExists) {
    $ToolboxConnectionsJson = & azd ai toolbox connection list `
        $Config.foundry_toolbox_name `
        --project-endpoint $Config.foundry_project_endpoint `
        --output json `
        --no-prompt
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect the existing Toolbox connections."
    }
    $ToolboxStateFile = Join-Path $GeneratedDirectory "toolbox-connections.json"
    $ToolboxConnectionsJson | Set-Content -Path $ToolboxStateFile -Encoding utf8
    Invoke-Checked {
        python -m foundry_databricks_genie.cli assert-toolbox-connections `
            --input $ToolboxStateFile `
            --expected-name $Config.foundry_connection_name
    } "The existing Toolbox does not match this configuration."
} else {
    Invoke-Checked {
        azd ai toolbox create `
            $Config.foundry_toolbox_name `
            --from-file $ToolboxFile `
            --project-endpoint $Config.foundry_project_endpoint `
            --output json `
            --no-prompt
    } "Could not create the Foundry Toolbox."
}

Write-Host ""
Write-Host "Setup completed."
Write-Host "Connection: $($Config.foundry_connection_name)"
Write-Host "Toolbox:    $($Config.foundry_toolbox_name)"
Write-Host ""
Write-Host "Next: attach the Toolbox to an agent, invoke Genie, and complete the"
Write-Host "Databricks OAuth consent flow when Foundry returns CONSENT_REQUIRED."
