[CmdletBinding()]
param(
    [string]$EnvFile,
    [switch]$ReplaceConnection,
    [switch]$Bootstrap,
    [switch]$Apply,
    [string]$QuestionFile,
    [switch]$ApproveTools,
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $EnvFile) {
    $EnvFile = Join-Path $RepoRoot ".env"
}

$PreviousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $RepoRoot "src"
    if ($Bootstrap -and $ReplaceConnection) {
        throw "Bootstrap does not permit connection replacement."
    }
    if (-not $Bootstrap -and ($Apply -or $QuestionFile -or $ApproveTools -or $NonInteractive)) {
        throw "Apply, QuestionFile, ApproveTools and NonInteractive require -Bootstrap."
    }
    $Command = if ($Bootstrap) { "bootstrap" } else { "setup" }
    $Arguments = @(
        "-m", "foundry_databricks_genie.cli", $Command,
        "--env-file", $EnvFile,
        "--output", (Join-Path $RepoRoot ".generated\toolbox.yaml")
    )
    if ($ReplaceConnection) {
        $Arguments += "--replace-connection"
    }
    if ($Apply) { $Arguments += "--apply" }
    if ($QuestionFile) { $Arguments += @("--question-file", $QuestionFile) }
    if ($ApproveTools) { $Arguments += "--approve-tools" }
    if ($NonInteractive) { $Arguments += "--non-interactive" }
    & python @Arguments
    if ($LASTEXITCODE -ne 0) {
        if ($Bootstrap) { exit $LASTEXITCODE }
        throw "Connector setup failed. See the configuration or operation error above."
    }
} finally {
    $env:PYTHONPATH = $PreviousPythonPath
}
