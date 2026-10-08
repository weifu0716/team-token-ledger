#requires -Version 7.0
param([ValidateSet('employee','boss')][string]$Mode='employee',[string]$TaskName)
if(-not $TaskName){$TaskName="TeamTokenDaily-$Mode"}
$task=Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if($task){Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue;Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false}
Write-Output '已移除排程，報告、設定與本機備份保留。'
