#!/bin/bash
# Installs the storage-scan launchd job for whichever machine this repo lives on.
# Safe to re-run: unloads any existing copy before reloading.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST_SRC="$REPO_DIR/launchd/com.day.storage-scan.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.day.storage-scan.plist"

mkdir -p "$HOME/Library/Logs/personal-automations"

sed -e "s|__REPO_DIR__|$REPO_DIR|g" -e "s|__HOME__|$HOME|g" "$PLIST_SRC" > "$PLIST_DEST"

launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"

echo "설치 완료: $PLIST_DEST"
echo "매일 09:00에 storage_optimizer scan이 실행됩니다."
