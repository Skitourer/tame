# TAME installer for Windows. Installs uv (which brings its own Python) if needed, then TAME.
# Usage, in PowerShell:  irm https://skitourer.github.io/tame/install.ps1 | iex
# Run it again to update.

# Not 'Stop': Windows PowerShell 5 turns any stderr line of uv into an error. Exit codes are
# checked instead.
$ErrorActionPreference = 'Continue'
$Package = 'git+https://github.com/skitourer/tame'

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host 'Installing uv, the tool that installs TAME and its Python...'
    powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw 'uv could not be installed. See https://docs.astral.sh/uv/getting-started/installation/'
    }
}

# Installs made before the package was named tame-tasks own the tk command: remove them.
$tools = (uv tool list 2>&1 | Out-String)
if ($tools -match '(?m)^tame v') {
    uv tool uninstall tame
}

Write-Host 'Installing TAME...'
uv tool install --upgrade $Package
if ($LASTEXITCODE -ne 0) { throw 'TAME could not be installed.' }

if (-not (Get-Command tk -ErrorAction SilentlyContinue)) {
    uv tool update-shell
    Write-Host ''
    Write-Host 'Done! Close this window, open a new terminal, and type: tk'
} else {
    Write-Host ''
    Write-Host 'Done! Type: tk'
}
