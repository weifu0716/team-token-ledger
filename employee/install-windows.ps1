#requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Enrollment,
    [string]$PythonPath = 'python',
    [string]$InstallDir = (Join-Path $env:USERPROFILE '.team-token-ledger'),
    [string]$CodexHome = $(if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }),
    [ValidateSet('labels','excerpts')][string]$ContentMode = 'labels',
    [string[]]$Project = @(),
    [switch]$AllowHttp,
    [string]$TaskName = 'TeamTokenLedger-Employee'
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$python = & $PythonPath -c 'import sys; assert sys.version_info >= (3,11); print(sys.executable)'
if ($LASTEXITCODE -ne 0 -or -not $python) { throw '需要 Python 3.11 以上。請先安裝，或傳入 -PythonPath。' }
$arguments = @((Join-Path $repo 'scripts/install.py'), '--enrollment', (Resolve-Path -LiteralPath $Enrollment).Path, '--install-dir', $InstallDir, '--codex-home', $CodexHome, '--content-mode', $ContentMode)
foreach ($projectPath in $Project) { $arguments += @('--project', $projectPath) }
if ($AllowHttp) { $arguments += '--allow-http' }
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw '安裝或首次回報失敗，沒有建立背景排程。' }
$target = (Resolve-Path -LiteralPath $InstallDir).Path
$runtime = Join-Path $target 'runtime'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
# Limit Windows ACLs on private files to the installing user and SYSTEM.
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $target /inheritance:r /grant:r "${identity}:(OI)(CI)F" 'SYSTEM:(OI)(CI)F' /Q | Out-Null
if ($LASTEXITCODE -ne 0) { throw '無法限制資料目錄存取權，請先修正 ACL 再啟用排程。' }
# Set protection only at the root. Children must inherit the private root ACL;
# removing inheritance recursively can leave regular files with an empty DACL.
Get-ChildItem -LiteralPath $target -Force | ForEach-Object {
    & icacls.exe $_.FullName /reset /T /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { throw '無法套用子目錄 ACL，尚未啟用排程。' }
}
$runner = Join-Path $runtime 'run-collector.ps1'
$escapeLiteral = { param($value) "'" + $value.Replace("'", "''") + "'" }
$runnerText = @"
`$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $(& $escapeLiteral (Join-Path $target 'app'))
& $(& $escapeLiteral $python) -m ledger collect --data $(& $escapeLiteral (Join-Path $target 'employee-data'))
exit `$LASTEXITCODE
"@
[System.IO.File]::WriteAllText($runner, $runnerText, [System.Text.UTF8Encoding]::new($true))
$pwsh = (Get-Process -Id $PID).Path
if ([System.IO.Path]::GetFileName($pwsh) -ne 'pwsh.exe') { throw '請用 PowerShell 7 執行此安裝程式。' }
$launcher = Join-Path $runtime 'hidden-launch.vbs'
$launchCommand = '"' + $pwsh + '" -NoProfile -NonInteractive -File "' + $runner + '"'
$vbs = 'Set sh = CreateObject("WScript.Shell")' + "`r`n" + 'WScript.Quit sh.Run("' + $launchCommand.Replace('"','""') + '", 0, True)' + "`r`n"
[System.IO.File]::WriteAllText($launcher, $vbs, [System.Text.Encoding]::Unicode)
$action = New-ScheduledTaskAction -Execute (Join-Path $env:SystemRoot 'System32/wscript.exe') -Argument ('"' + $launcher + '"')
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) -RepetitionInterval (New-TimeSpan -Minutes 5)
$logon = New-ScheduledTaskTrigger -AtLogOn -User $identity
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 4) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($trigger,$logon) -Settings $settings -Principal $principal -Force | Out-Null
$before = (Get-ScheduledTaskInfo -TaskName $TaskName).LastRunTime
Start-ScheduledTask -TaskName $TaskName
$deadline = (Get-Date).AddSeconds(45)
do {
    Start-Sleep -Milliseconds 500
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    $state = (Get-ScheduledTask -TaskName $TaskName).State
} until (($info.LastRunTime -gt $before -and $state -ne 'Running' -and $info.LastTaskResult -eq 0) -or (Get-Date) -gt $deadline)
if ($info.LastRunTime -le $before -or $info.LastTaskResult -ne 0 -or $state -eq 'Running') { throw "排程已建立但驗證未完成。LastRunTime=$($info.LastRunTime); LastTaskResult=$($info.LastTaskResult); State=$state。請查看工作排程器與 employee-data/status.json。" }
$status = Get-Content -LiteralPath (Join-Path $target 'employee-data/status.json') -Raw | ConvertFrom-Json
Write-Output "安裝完成。排程：$TaskName；LastRunTime=$($info.LastRunTime)；LastTaskResult=$($info.LastTaskResult)；狀態=$($status.phase)"
Write-Output '每 5 分鐘由一般程式回報；不呼叫 AI。電腦關機或登出時不執行。'
