"""Rolling-window sustained drift detection (proactive guardian)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from focus_guardian.analyzer import (
    classify_capture,
    load_recent_records,
    longest_streak_minutes,
)
from focus_guardian.clipboard_intel import (
    latest_transcription_excerpt,
    proactive_cfg,
    recent_transcriptions,
)
from focus_guardian.drift_config import enrich_drift_with_api, rule_enabled
from focus_guardian.familiar import stills_root


@dataclass
class DriftAssessment:
    checked_at: str
    should_chime: bool
    reason: str
    evidence: str
    suggested_nudge: str
    codes: list[str]
    wispr_excerpt: str

    def to_dict(self) -> dict:
        return {
            "checked_at": self.checked_at,
            "should_chime": self.should_chime,
            "reason": self.reason,
            "evidence": self.evidence,
            "suggested_nudge": self.suggested_nudge,
            "codes": self.codes,
            "wispr_excerpt": self.wispr_excerpt,
        }


def _topic_threshold(cfg: dict) -> float:
    return float(proactive_cfg(cfg).get("topicScoreLow", 0.35))


def _wispr_off_topic_minutes(utterances, cfg: dict) -> float:
    """Minutes span of consecutive low-topic transcriptions."""
    if not utterances:
        return 0.0
    low = _topic_threshold(cfg)
    sustained = 0.0
    run_start: datetime | None = None
    for u in utterances:
        if u.topic_score < low:
            if run_start is None:
                run_start = u.start
            sustained = max(sustained, (u.end - run_start).total_seconds() / 60)
        else:
            run_start = None
    return sustained


def _topic_pivot(utterances, cfg: dict) -> bool:
    """New Wispr text introduces unrelated domain vs goal keywords."""
    if len(utterances) < 2:
        return False
    keys = set()
    for k in cfg.get("goalKeywords", []) or []:
        keys.add(k.lower())
    for k in cfg.get("assignmentKeywords", []) or []:
        keys.add(k.lower())
    goal = (cfg.get("currentGoal") or "").lower()
    for word in re.findall(r"[a-zA-Z]{4,}", goal):
        keys.add(word)
    if not keys:
        return False

    prev = utterances[-2]
    latest = utterances[-1]
    if latest.topic_score >= _topic_threshold(cfg):
        return False
    prev_blob = prev.text.lower()
    latest_blob = latest.text.lower()
    prev_hits = {k for k in keys if k in prev_blob}
    latest_hits = {k for k in keys if k in latest_blob}
    if prev_hits and not latest_hits and len(latest.text) > 100:
        return True
    off = cfg.get("distractionTitlePatterns", []) + (cfg.get("antiPatterns") or [])
    off_in_latest = sum(1 for p in off if p.lower() in latest_blob)
    return off_in_latest >= 2 and latest.topic_score < 0.4


def evaluate_drift(cfg: dict) -> DriftAssessment:
    p = proactive_cfg(cfg)
    window = int(p.get("evaluationWindowMinutes", 30))
    sustained_min = float(p.get("driftSustainedMinutes", 10))
    th = cfg.get("thresholds", {})
    now = datetime.now()
    root = stills_root(cfg)
    records = load_recent_records(root, window)
    utterances = recent_transcriptions(cfg, window_minutes=window)

    codes: list[str] = []
    evidence_parts: list[str] = []
    severity_rank = 0  # 0 none, 1 medium, 2 high

    wispr_mins = _wispr_off_topic_minutes(utterances, cfg)
    if rule_enabled(cfg, "wisprOffTopic") and wispr_mins >= sustained_min:
        codes.append("wispr_off_topic")
        evidence_parts.append(
            f"~{wispr_mins:.0f} min of off-goal dictation (Wispr/clipboard)."
        )
        severity_rank = max(severity_rank, 2)

    if rule_enabled(cfg, "topicPivot") and _topic_pivot(utterances, cfg):
        codes.append("topic_pivot")
        evidence_parts.append("Latest dictation pivoted away from your assignment goal.")
        severity_rank = max(severity_rank, 2)

    distraction_mins = longest_streak_minutes(records, {"distraction"}, cfg)
    if rule_enabled(cfg, "distractionStreak") and distraction_mins >= th.get(
        "distractionMinutes", 10
    ):
        codes.append("distraction_streak")
        evidence_parts.append(f"~{distraction_mins:.0f} min on distraction surfaces.")
        severity_rank = max(severity_rank, 2)

    ai_mins = longest_streak_minutes(records, {"ai_chat", "research"}, cfg)
    build_mins = longest_streak_minutes(records, {"build"}, cfg)
    if rule_enabled(cfg, "aiLoop") and ai_mins >= th.get("aiLoopMinutes", 18) and build_mins < 3:
        codes.append("ai_research_loop")
        evidence_parts.append(
            f"~{ai_mins:.0f} min AI/research; almost no build time."
        )
        severity_rank = max(severity_rank, 1)

    polish_mins = longest_streak_minutes(records, {"polish"}, cfg)
    if (
        rule_enabled(cfg, "polishSpiral")
        and polish_mins >= th.get("slidesWithoutBuildMinutes", 25)
        and build_mins < 5
    ):
        codes.append("polish_without_build")
        evidence_parts.append(
            f"~{polish_mins:.0f} min polish; only ~{build_mins:.0f} min building."
        )
        severity_rank = max(severity_rank, 1)

    # High-confidence spike: fresh off-topic Wispr + distraction surface now
    latest = utterances[-1] if utterances else None
    recent_distraction = (
        records
        and classify_capture(records[-1][1], records[-1][2], cfg) == "distraction"
    )
    if (
        rule_enabled(cfg, "wisprDistractionSpike")
        and latest
        and latest.topic_score < 0.25
        and len(latest.text) >= int(p.get("wisprMinChars", 80))
        and recent_distraction
        and (now - latest.end).total_seconds() < 300
    ):
        codes.append("wispr_distraction_spike")
        evidence_parts.append("Off-topic dictation while on a distraction surface.")
        severity_rank = max(severity_rank, 2)

    excerpt = latest_transcription_excerpt(cfg)
    should_chime = False
    reason = "On track in the evaluation window."
    suggested = ""

    if severity_rank >= 2:
        sustained_ok = wispr_mins >= sustained_min or distraction_mins >= th.get(
            "distractionMinutes", 10
        )
        spike = "wispr_distraction_spike" in codes
        should_chime = sustained_ok or spike
        reason = "Sustained drift from your goal."
        suggested = _nudge_for_codes(codes, cfg)
    elif severity_rank == 1:
        # Medium patterns need sustained screen time, not a single blip
        if ai_mins >= sustained_min or polish_mins >= sustained_min:
            should_chime = True
            reason = "Research or polish spiral without building."
            suggested = _nudge_for_codes(codes, cfg)

    evidence = " ".join(evidence_parts) if evidence_parts else "No drift signals."
    if excerpt and should_chime:
        evidence = f'You said: "{excerpt}" — {evidence}'

    # Optional semantic layer (API): sentiment + reduce false positives
    if should_chime and codes:
        enriched = enrich_drift_with_api(
            goal=cfg.get("currentGoal", ""),
            wispr_excerpt=excerpt,
            evidence=evidence,
            codes=codes,
            cfg=cfg,
        )
        if enriched is not None:
            if enriched.get("summary"):
                reason = enriched["summary"]
            if enriched.get("nudge"):
                suggested = enriched["nudge"]
            if enriched.get("sentiment") and enriched["sentiment"] != "focused":
                evidence = f"[{enriched['sentiment']}] {evidence}"
            if enriched.get("should_chime") is False:
                should_chime = False
                reason = "On track (semantic check)."
                suggested = ""

    return DriftAssessment(
        checked_at=now.isoformat(timespec="seconds"),
        should_chime=should_chime,
        reason=reason,
        evidence=evidence[:400],
        suggested_nudge=suggested,
        codes=codes,
        wispr_excerpt=excerpt,
    )


def _nudge_for_codes(codes: list[str], cfg: dict) -> str:
    goal = cfg.get("currentGoal", "your goal")
    actions = {
        "wispr_off_topic": f"Close unrelated tabs. One sentence on {goal}, then 25 min on the deliverable only.",
        "topic_pivot": "You pivoted off-topic. Re-open the assignment brief and do the next concrete step.",
        "distraction_streak": "Close the distraction. Open your build surface and set a 25-minute timer.",
        "ai_research_loop": "Stop chatting. Write 3 trade-offs, then ship one proof in your build tool.",
        "polish_without_build": "Freeze slides. Ship one working proof before more polish.",
        "wispr_distraction_spike": "You drifted in speech and on screen. Return to the primary artifact now.",
    }
    for code in codes:
        if code in actions:
            return actions[code]
    return f"Return to: {goal}. Next 25 min: one deliverable only."
