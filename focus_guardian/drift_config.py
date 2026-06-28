"""User-configurable drift rules and optional semantic layer."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from focus_guardian.clipboard_intel import topic_score


def drift_rules(cfg: dict) -> dict:
    defaults = {
        "wisprOffTopic": True,
        "distractionStreak": True,
        "aiLoop": True,
        "polishSpiral": True,
        "topicPivot": True,
        "wisprDistractionSpike": True,
        "offTopicPhrases": [],
        "onTopicPhrases": [],
        "sentimentEnabled": True,
        "useApiForDrift": False,
    }
    return {**defaults, **cfg.get("driftRules", {})}


def rule_enabled(cfg: dict, name: str) -> bool:
    return bool(drift_rules(cfg).get(name, True))


def phrase_penalty(text: str, cfg: dict) -> float:
    """Adjust topic score from configured phrase lists (0 = neutral)."""
    rules = drift_rules(cfg)
    blob = text.lower()
    penalty = 0.0
    for p in rules.get("offTopicPhrases") or []:
        if p.lower() in blob:
            penalty += 0.2
    boost = 0.0
    for p in rules.get("onTopicPhrases") or []:
        if p.lower() in blob:
            boost += 0.15
    return min(0.5, penalty) - min(0.3, boost)


def adjusted_topic_score(text: str, cfg: dict) -> float:
    base = topic_score(text, cfg)
    adj = base - phrase_penalty(text, cfg)
    return max(0.0, min(1.0, round(adj, 3)))


def enrich_drift_with_api(
    *,
    goal: str,
    wispr_excerpt: str,
    evidence: str,
    codes: list[str],
    cfg: dict,
) -> dict | None:
    """Optional LLM pass: sentiment + whether drift is real vs false positive."""
    rules = drift_rules(cfg)
    if not rules.get("useApiForDrift") or not os.environ.get("ANTHROPIC_API_KEY"):
        return None

    model = cfg.get("synthesis", {}).get("model") or os.environ.get(
        "FOCUS_GUARDIAN_MODEL", "claude-sonnet-4-20250514"
    )
    payload = {
        "goal": goal,
        "wispr_excerpt": wispr_excerpt,
        "evidence": evidence,
        "codes": codes,
        "off_topic_phrases": rules.get("offTopicPhrases", []),
        "on_topic_phrases": rules.get("onTopicPhrases", []),
    }
    system = """You judge work-session drift for a focus coach.
Return ONLY valid JSON:
{"should_chime": bool, "sentiment": "focused|anxious|avoidant|frustrated|neutral",
 "summary": "one sentence human explanation",
 "nudge": "one sentence next action"}
Be conservative: should_chime true only if clearly off-goal or stuck, not normal thinking aloud."""
    body = {
        "model": model,
        "max_tokens": 300,
        "system": system,
        "messages": [{"role": "user", "content": json.dumps(payload)}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = "".join(
            b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
        )
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
        return json.loads(text)
    except (urllib.error.HTTPError, json.JSONDecodeError, KeyError):
        return None
