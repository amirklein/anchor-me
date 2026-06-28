#!/bin/bash
# Install macOS LaunchAgent to run Focus Guardian proactive daemon at login.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${REPO}/.venv/bin/python"
PLIST_SRC="${REPO}/scripts/com.focusguardian.guardian.plist.template"
PLIST_DST="${HOME}/Library/LaunchAgents/com.focusguardian.guardian.plist"

if [[ ! -x "${PYTHON}" ]]; then
  echo "Create venv first: cd ${REPO} && python3 -m venv .venv && pip install -e ."
  exit 1
fi

mkdir -p "${HOME}/Library/LaunchAgents"
sed -e "s|@PYTHON@|${PYTHON}|g" \
    -e "s|@REPO@|${REPO}|g" \
    -e "s|USER_PLACEHOLDER|${USER}|g" \
  "${PLIST_SRC}" > "${PLIST_DST}"

launchctl unload "${PLIST_DST}" 2>/dev/null || true
launchctl load "${PLIST_DST}"
echo "Installed LaunchAgent (proactive guardian). Logs: ~/.focus-guardian/state/launchd.log"
echo "Ensure config has interventionMode: proactive (fg profile job_search)"
