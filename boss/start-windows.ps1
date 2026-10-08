#requires -Version 7.0
param([string]$PythonPath='python',[string]$Data=(Join-Path $env:USERPROFILE '.team-token-ledger/boss'),[int]$Port=8765)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
& $PythonPath -m ledger server --data $Data --port $Port
exit $LASTEXITCODE
