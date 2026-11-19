<#
.SYNOPSIS
    Run the development version of tame on throwaway data, never your real tasks.

.DESCRIPTION
    Tasks and settings go to .sandbox\ at the repository root (ignored by git).
    All arguments are passed to tk. Quote '--' (PowerShell eats a bare --).

.EXAMPLE
    .\scripts\tk.ps1 add Call bank +phone due:fri
    .\scripts\tk.ps1
    .\scripts\tk.ps1 add '--' done the report
    .\scripts\tk.ps1 --reset      # delete the sandbox and start over
#>
$root = Split-Path -Parent $PSScriptRoot
$sandbox = Join-Path $root '.sandbox'
if ($args.Count -eq 1 -and $args[0] -eq '--reset') {
    Remove-Item -Recurse -Force $sandbox -ErrorAction SilentlyContinue
    Write-Host "Sandbox reset: $sandbox"
    exit 0
}
$env:TAME_HOME = $sandbox
$env:UV_TOOL_BIN_DIR = Join-Path $sandbox 'bin'  # tk alias stays in the sandbox too
uv run --project $root tk @args
exit $LASTEXITCODE
