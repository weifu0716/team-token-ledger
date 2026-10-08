#requires -Version 7.0
[CmdletBinding()]
param(
 [ValidateSet('employee','boss')][string]$Mode='employee',
 [Parameter(Mandatory)][string]$SharedFolder,
 [string]$Name,
 [string]$Roster,
 [string]$PythonPath='python',
 [string]$InstallDir,
 [string]$CodexHome=$(if($env:CODEX_HOME){$env:CODEX_HOME}else{Join-Path $env:USERPROFILE '.codex'}),
 [ValidateSet('labels','excerpts')][string]$ContentMode='labels',
 [string]$ReportTime,
 [string[]]$Project=@(),
 [string]$TaskName,
 [switch]$UseExistingPython
)
$ErrorActionPreference='Stop'
$env:PYTHONIOENCODING='utf-8'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$repo=Split-Path $PSScriptRoot -Parent
if(-not $InstallDir){$InstallDir=Join-Path $env:USERPROFILE ".team-token-daily-$Mode"}
if(-not $TaskName){$TaskName="TeamTokenDaily-$Mode"}
if(-not $ReportTime){$ReportTime=if($Mode -eq 'boss'){'17:15'}else{'17:00'}}
if($Mode -eq 'employee' -and -not $Name){$Name=Read-Host '日報上的員工姓名'}
if($Mode -eq 'boss' -and -not $Roster){throw '老闆端需提供 -Roster 名單文字檔，每行一個姓名。'}
$python=& $PythonPath -c 'import sys; assert sys.version_info >= (3,11); print(sys.executable)'
if($LASTEXITCODE -ne 0 -or -not $python){throw '需要Python 3.11以上，請先安裝或指定-PythonPath。'}
$existingTask=Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if($existingTask){
 $expectedLauncher=Join-Path ([IO.Path]::GetFullPath($InstallDir)) 'runtime/hidden-launch.vbs'
 if(-not ($existingTask.Actions.Arguments -contains ('"'+$expectedLauncher+'"'))){throw '同名排程不屬於這個安裝目錄，拒絕覆蓋。'}
 Stop-ScheduledTask -TaskName $TaskName
}
$argsList=@((Join-Path $repo 'scripts/install_daily.py'),'--mode',$Mode,'--shared',$SharedFolder,'--install-dir',$InstallDir,'--time',$ReportTime,'--offset',([int][DateTimeOffset]::Now.Offset.TotalMinutes).ToString(),'--codex-home',$CodexHome,'--content-mode',$ContentMode)
if($Name){$argsList+=@('--name',$Name)}
if($Roster){$argsList+=@('--roster',$Roster)}
foreach($projectPath in $Project){$argsList+=@('--project',$projectPath)}
& $python @argsList
if($LASTEXITCODE -ne 0){throw '設定未完成，未建立排程。'}
$target=(Resolve-Path -LiteralPath $InstallDir).Path
if(-not $UseExistingPython){
 & $python -m venv (Join-Path $target 'venv')
 if($LASTEXITCODE -ne 0){throw '無法建立獨立Python環境'}
 $python=Join-Path $target 'venv/Scripts/python.exe'
 & $python -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
 if($LASTEXITCODE -ne 0){throw 'PDF套件安裝失敗，未建立排程'}
}
& $python -c 'import reportlab'
if($LASTEXITCODE -ne 0){throw '缺少ReportLab，未建立排程'}
$runtime=Join-Path $target 'runtime'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$pwsh=(Get-Process -Id $PID).Path
$quote={param($s) "'"+$s.Replace("'","''")+"'"}
$runner=Join-Path $runtime 'run.ps1'
$extra=if($Mode -eq 'boss'){'boss'}else{''}
$logPath=Join-Path $target 'data/last-run.log'
$script="`$ErrorActionPreference='Stop'`r`n`$env:PYTHONIOENCODING='utf-8'`r`n[Console]::OutputEncoding=[Text.UTF8Encoding]::new(`$false)`r`n(Get-Date -Format o) | Set-Content -Encoding utf8 $(& $quote $logPath)`r`n& $(& $quote $python) $(& $quote (Join-Path $target 'run_daily.py')) $extra 2>&1 | Out-File -Append -Encoding utf8 $(& $quote $logPath)`r`n`$result=`$LASTEXITCODE`r`n`"Completed exit=`$result`" | Out-File -Append -Encoding utf8 $(& $quote $logPath)`r`nexit `$result`r`n"
[IO.File]::WriteAllText($runner,$script,[Text.UTF8Encoding]::new($true))
$manual=Join-Path $runtime 'manual.ps1'
$manualScript=if($Mode -eq 'boss'){$script}else{
 "param([string]`$Day=(Get-Date -Format 'yyyy-MM-dd'))`r`n& $(& $quote $python) $(& $quote (Join-Path $target 'run_daily.py')) --day `$Day`r`nexit `$LASTEXITCODE`r`n"
}
[IO.File]::WriteAllText($manual,$manualScript,[Text.UTF8Encoding]::new($true))
$shell=New-Object -ComObject WScript.Shell
$shortcut=$shell.CreateShortcut((Join-Path $target $(if($Mode -eq 'boss'){'立即檢查收件.lnk'}else{'立即補交今天.lnk'})))
$shortcut.TargetPath=$pwsh
$shortcut.Arguments='-NoProfile -File "'+$manual+'"'
$shortcut.WorkingDirectory=$target
$shortcut.Save()
if($Mode -eq 'boss'){New-Item -ItemType Directory -Force -Path (Join-Path $target 'results') | Out-Null}
$launcher=Join-Path $runtime 'hidden-launch.vbs'
$command='"'+$pwsh+'" -NoProfile -NonInteractive -File "'+$runner+'"'
[IO.File]::WriteAllText($launcher,'Set sh = CreateObject("WScript.Shell")'+"`r`n"+'WScript.Quit sh.Run("'+$command.Replace('"','""')+'", 0, True)',[Text.Encoding]::Unicode)
& $python (Join-Path $target 'run_daily.py') seal
if($LASTEXITCODE -ne 0){throw '程式指紋建立失敗'}
$identity=[Security.Principal.WindowsIdentity]::GetCurrent().Name
$action=New-ScheduledTaskAction -Execute (Join-Path $env:SystemRoot 'System32/wscript.exe') -Argument ('"'+$launcher+'"')
$daily=New-ScheduledTaskTrigger -Daily -At $ReportTime
$retry=New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(30) -RepetitionInterval (New-TimeSpan -Minutes 30)
$logon=New-ScheduledTaskTrigger -AtLogOn -User $identity
$settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal=New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($daily,$retry,$logon) -Settings $settings -Principal $principal -Force | Out-Null
$before=(Get-ScheduledTaskInfo -TaskName $TaskName).LastRunTime
Start-ScheduledTask -TaskName $TaskName
$deadline=(Get-Date).AddSeconds(90)
do{
 Start-Sleep -Milliseconds 500
 $info=Get-ScheduledTaskInfo -TaskName $TaskName
 $state=(Get-ScheduledTask -TaskName $TaskName).State
}until(($info.LastRunTime -gt $before -and $state -ne 'Running' -and $info.LastTaskResult -eq 0) -or (Get-Date) -gt $deadline)
if($info.LastRunTime -le $before -or $info.LastTaskResult -ne 0 -or $state -eq 'Running'){throw "排程驗收未通過：LastRunTime=$($info.LastRunTime)，LastTaskResult=$($info.LastTaskResult)。設定保留，請查data狀態檔。"}
Write-Output "排程已真實執行：$TaskName；LastRunTime=$($info.LastRunTime)；LastTaskResult=0。"
Write-Output "每日${ReportTime}執行，登入及每30分鐘檢查補交；未到日報時間不產生今天的正式報告。"
Write-Output "手動補交／收件檢查：pwsh -File `"$manual`""
