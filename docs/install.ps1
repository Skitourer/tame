# TAME installer for Windows. Installs uv (which brings its own Python) if needed, then TAME.
# Usage, in PowerShell:  irm https://skitourer.github.io/tame/install.ps1 | iex
# Run it again to update.

$ErrorActionPreference = 'Stop'
$Package = 'git+https://github.com/skitourer/tame'

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host 'Installing uv, the tool that installs TAME and its Python...'
    powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw 'uv could not be installed. See https://docs.astral.sh/uv/getting-started/installation/'
    }
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
