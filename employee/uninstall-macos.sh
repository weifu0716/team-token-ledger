#!/bin/bash
set -euo pipefail
PLIST="$HOME/Library/LaunchAgents/com.teamtokenledger.employee.plist"
if [[ -f "$PLIST" ]]; then
  launchctl bootout "gui/$(id -u)" "$PLIST" || true
  rm -- "$PLIST"
fi
printf '%s\n' '已移除背景回報。個人資料目錄保留；請老闆撤銷配對憑證。'
