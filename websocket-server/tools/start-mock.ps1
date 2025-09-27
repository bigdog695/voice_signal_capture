Param(
  [int]$Port = 18000
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here

Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-Not (Test-Path $python)) {
  Write-Error ".venv not found. Create it first: python -m venv .venv"
}

$env:MOCK_SERVER_PORT = "$Port"

Start-Process -NoNewWindow -FilePath $python -ArgumentList "mock_server.py" -WorkingDirectory $root
Write-Output "Mock server starting on port $Port"
