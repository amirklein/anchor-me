"""Optional LLM coaching layer (works from any terminal / Claude Code)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from focus_guardian.analyzer import Report

SYSTEM = """You are Focus Guardian, a direct productivity coach.
The user pairs you with Familiar (screen activity summaries). You receive a JSON report of recent behavior patterns.
Rules:
- Under 120 words.
- Name the drift pattern concretely from the evidence.
- Give exactly ONE next action for the next 25 minutes tied to their stated goal.
- No generic advice. No bullet lists longer than 3 items.
- Tone: firm, supportive, senior colleague — not preachy."""


def format_prompt(report: Report, narrative: str | None = None) -> str:
    payload = report.to_dict()
    parts = [f"Goal: {report.goal}", ""]
    if narrative:
        parts.extend([narrative, ""])
    parts.extend(
        [
            f"Report JSON:\n{json.dumps(payload, indent=2)}",
            "",
            "What should they do right now?",
        ]
    )
    return "\n".join(parts)


def coach_with_api(report: Report, model: str | None = None) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("Set ANTHROPIC_API_KEY for API coaching, or use: fgr coach --print")

    model = model or os.environ.get("FOCUS_GUARDIAN_MODEL", "claude-sonnet-4-20250514")
    body = {
        "model": model,
        "max_tokens": 400,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": format_prompt(report)}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Anthropic API error: {err}") from e

    blocks = data.get("content") or []
    texts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
    return "\n".join(texts).strip() or "(empty response)"


def coach_drift_nudge(assessment, cfg: dict) -> str:
    """Offline nudge for proactive drift chime."""
    from focus_guardian.drift import DriftAssessment

    if not isinstance(assessment, DriftAssessment):
        return ""
    if assessment.suggested_nudge:
        return assessment.suggested_nudge
    goal = cfg.get("currentGoal", "your goal")
    return f"Return to: {goal}. Next 25 min: one concrete deliverable."


def coach_offline(report: Report) -> str:
    """Deterministic coaching when no API key is available."""
    if not report.findings:
        return (
            f"On track (~{report.on_track_ratio:.0%} aligned). "
            f"Stay on: {report.goal}. Next 25 min: continue the primary artifact only."
        )
    f = max(report.findings, key=lambda x: {"info": 0, "warn": 1, "critical": 2}[x.severity])
    actions = {
        "distraction_streak": "Close the distraction tab. Open your primary work surface and set a 25-minute timer.",
        "context_switch_burst": "Pick ONE window. Write the next concrete deliverable in one sentence, then execute only that.",
        "ai_research_loop": "Stop chatting. Write 5 bullets: problem, recommendation, 3 trade-offs. Then build one proof.",
        "polish_without_build": "Freeze slides/mockups. Ship one working proof in your build tool first.",
        "goal_drift": "Re-read your goal aloud. Do the smallest step that directly advances it — nothing else.",
        "wispr_off_topic": "Your dictation drifted off goal. Close unrelated tabs; 25 min on the deliverable only.",
        "topic_pivot": "You pivoted topics in speech. Re-open the assignment brief and do the next concrete step.",
        "wispr_distraction_spike": "Off-topic speech on a distraction surface. Close it and open your build tool.",
    }
    action = actions.get(f.code, "Return to your stated goal for 25 minutes with one deliverable.")
    return f"{f.message} {f.evidence}\n\nNext 25 min: {action}"
