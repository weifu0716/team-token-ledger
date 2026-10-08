#requires -Version 7.0
param([string]$TaskName = 'TeamTokenLedger-Employee')
$ErrorActionPreference = 'Stop'
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
Write-Output '已停止並移除背景排程。資料保留在安裝目錄；請老闆在看板撤銷這台電腦的上傳權限。'
