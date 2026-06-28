"""Desktop notifications (macOS first)."""

from __future__ import annotations

import platform
import shutil
import subprocess
from datetime import datetime

from focus_guardian.analyzer import Report
from focus_guardian.paths import last_notify_path, log_path


def _escape_apple(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def notify_macos(title: str, subtitle: str, body: str) -> bool:
    if platform.system() != "Darwin":
        return False
    script = (
        f'display notification "{_escape_apple(body)}" '
        f'with title "{_escape_apple(title)}" '
        f'subtitle "{_escape_apple(subtitle)}"'
    )
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def notify_linux(body: str, title: str = "Focus Guardian") -> bool:
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", title, body], check=False)
        return True
    return False


def should_skip_cooldown(cooldown_minutes: int) -> bool:
    p = last_notify_path()
    if not p.exists():
        return False
    try:
        last = int(p.read_text(encoding="utf-8").strip())
    except ValueError:
        return False
    elapsed = datetime.now().timestamp() - last
    return elapsed < cooldown_minutes * 60


def mark_notified() -> None:
    last_notify_path().write_text(str(int(datetime.now().timestamp())), encoding="utf-8")
    with log_path().open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')} notified\n")


def _chime_cooldown_minutes(cfg: dict) -> int:
    p = {**cfg.get("proactive", {}), **cfg}
    return int(p.get("chimeCooldownMinutes", p.get("cooldownMinutes", 25)))


def notify_drift_chime(assessment, nudge: str, cfg: dict) -> bool:
    """macOS notification when proactive drift is sustained."""
    from focus_guardian.drift import DriftAssessment

    if not isinstance(assessment, DriftAssessment):
        return False
    if not assessment.should_chime:
        return False
    if should_skip_cooldown(_chime_cooldown_minutes(cfg)):
        return False

    title = "Focus Guardian"
    subtitle = assessment.wispr_excerpt[:120] if assessment.wispr_excerpt else (
        cfg.get("currentGoal", "")[:120]
    )
    body = f"{assessment.reason} {nudge}"[:250]

    sent = notify_macos(title, subtitle, body) or notify_linux(body, title)
    if sent:
        mark_notified()
    return sent


def maybe_notify(report: Report, cfg: dict) -> bool:
    if not report.should_notify:
        return False
    cooldown = int(cfg.get("cooldownMinutes", 20))
    if should_skip_cooldown(cooldown):
        return False

    title = "Focus Guardian"
    subtitle = (report.goal or "")[:120]
    body = report.summary
    if report.findings:
        body = f"{body} — {report.findings[0].evidence}"[:250]

    sent = notify_macos(title, subtitle, body[:200]) or notify_linux(body, title)
    if sent:
        mark_notified()
    return sent
