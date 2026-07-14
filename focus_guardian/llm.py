"""Optional LLM intent parsing for Slack commands."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

INTENT_SYSTEM = """You classify Focus Guardian Slack messages into structured intents.
Return ONLY valid JSON: {"action": "<name>", "args": {...}}.

Actions:
- set_focus: args {text, cadence?} — user sets day/week/month focus
- show_focus: no args
- clear_focus: args {cadence: day|week|month}
- set_week: args {preset: mon-fri|sun-thu|sun-sat|mon-sun}
- status: no args
- review: no args — retrospective recap
- drift: no args — am I drifting now
- snooze: args {duration: natural language like "2 hours" or "until 3pm"}
- resume: no args — resume alerts
- help: no args
- unknown: no args

Use context (active focus, last drift) to disambiguate. Prefer set_focus when user describes goals."""


def _anthropic_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or None


def parse_intent(message: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Return {action, args} via Anthropic when API key set; else None (use heuristics)."""
    api_key = _anthropic_key()
    if not api_key:
        return None

    context = context or {}
    model = os.environ.get("FOCUS_GUARDIAN_MODEL", "claude-sonnet-4-20250514")
    user_content = json.dumps({"message": message, "context": context}, indent=2)
    body = {
        "model": model,
        "max_tokens": 256,
        "system": INTENT_SYSTEM,
        "messages": [{"role": "user", "content": user_content}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return None

    text = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            text += block.get("text", "")

    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "action" in parsed:
            parsed.setdefault("args", {})
            return parsed
    except json.JSONDecodeError:
        pass
    return None
