"""Wispr / clipboard intelligence — primary intent signal from Familiar."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from focus_guardian.familiar import parse_capture_time, read_frontmatter, stills_root


@dataclass
class Utterance:
    start: datetime
    end: datetime
    text: str
    topic_score: float
    source_paths: list[str]
    wispr_nearby: bool


def proactive_cfg(cfg: dict) -> dict:
    return {**cfg.get("proactive", {}), **cfg}


def _max_clipboard_chars(cfg: dict) -> int:
    p = proactive_cfg(cfg)
    return int(p.get("maxClipboardChars", 8000))


def _wispr_min_chars(cfg: dict) -> int:
    p = proactive_cfg(cfg)
    return int(p.get("wisprMinChars", 80))


def _keyword_set(cfg: dict) -> set[str]:
    keys = set()
    for k in cfg.get("goalKeywords", []) or []:
        keys.add(k.lower().strip())
    for k in cfg.get("assignmentKeywords", []) or []:
        keys.add(k.lower().strip())
    goal = cfg.get("currentGoal", "") or ""
    for word in re.findall(r"[a-zA-Z]{3,}", goal.lower()):
        keys.add(word)
    return keys


def topic_score(text: str, cfg: dict) -> float:
    """0..1 alignment with stated goal keywords."""
    if not text or len(text.strip()) < 10:
        return 0.5
    blob = text.lower()
    keys = _keyword_set(cfg)
    if not keys:
        return 0.5

    hits = sum(1 for k in keys if k in blob)
    score = min(1.0, hits / max(2, len(keys) * 0.15))

    off_topic = (
        cfg.get("distractionTitlePatterns", [])
        + (cfg.get("antiPatterns") or [])
        + (cfg.get("driftRules", {}).get("offTopicPhrases") or [])
    )
    off_hits = sum(1 for p in off_topic if p.lower() in blob)
    if off_hits >= 2:
        score = max(0.0, score - 0.35)
    elif off_hits == 1:
        score = max(0.0, score - 0.15)

    on_topic = cfg.get("driftRules", {}).get("onTopicPhrases") or []
    on_hits = sum(1 for p in on_topic if p.lower() in blob)
    if on_hits >= 1:
        score = min(1.0, score + 0.1 * on_hits)

    return round(score, 3)


def _screen_near_wispr(root: Path, ts: datetime, window_sec: int = 120) -> bool:
    """True if a screen capture near ts shows Wispr Flow."""
    lo = ts - timedelta(seconds=window_sec)
    hi = ts + timedelta(seconds=window_sec)
    for session in root.iterdir():
        if not session.is_dir():
            continue
        for md in session.glob("*.md"):
            t = parse_capture_time(md.stem)
            if t is None or t < lo or t > hi:
                continue
            fm = read_frontmatter(md)
            app = fm.get("app", "").lower()
            title = fm.get("window_title_norm", fm.get("window_title_raw", "")).lower()
            if "wispr" in app or "wispr" in title:
                return True
    return False


def load_clipboard_events(
    root: Path,
    since: datetime,
    until: datetime | None,
    cfg: dict,
) -> list[tuple[datetime, str, Path, bool]]:
    """Returns (ts, text, path, wispr_nearby)."""
    until = until or datetime.now()
    max_chars = _max_clipboard_chars(cfg)
    min_wispr = _wispr_min_chars(cfg)
    out: list[tuple[datetime, str, Path, bool]] = []

    for session in root.iterdir():
        if not session.is_dir() or not session.name.startswith("session-"):
            continue
        for path in session.glob("*.clipboard.txt"):
            stem = path.name.replace(".clipboard.txt", "")
            ts = parse_capture_time(stem)
            if ts is None or ts < since or ts > until:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").strip()
            if not text:
                continue
            wispr = len(text) >= min_wispr or _screen_near_wispr(root, ts)
            out.append((ts, text[:max_chars], path, wispr))

    out.sort(key=lambda x: x[0])
    return out


def merge_utterances(
    events: list[tuple[datetime, str, Path, bool]],
    cfg: dict,
    *,
    merge_gap_minutes: float = 2.0,
) -> list[Utterance]:
    if not events:
        return []

    merged: list[Utterance] = []
    batch_ts: list[datetime] = []
    batch_text: list[str] = []
    batch_paths: list[str] = []
    batch_wispr = False

    def flush() -> None:
        if not batch_text:
            return
        text = "\n".join(batch_text).strip()
        if len(text) < 10:
            return
        from focus_guardian.drift_config import adjusted_topic_score

        u = Utterance(
            start=batch_ts[0],
            end=batch_ts[-1],
            text=text,
            topic_score=adjusted_topic_score(text, cfg),
            source_paths=batch_paths,
            wispr_nearby=batch_wispr,
        )
        merged.append(u)

    for ts, text, path, wispr in events:
        if batch_ts and (ts - batch_ts[-1]).total_seconds() / 60 > merge_gap_minutes:
            flush()
            batch_ts, batch_text, batch_paths, batch_wispr = [], [], [], False
        batch_ts.append(ts)
        batch_text.append(text)
        batch_paths.append(str(path))
        batch_wispr = batch_wispr or wispr

    flush()
    return merged


def recent_transcriptions(cfg: dict, window_minutes: int | None = None) -> list[Utterance]:
    root = stills_root(cfg)
    p = proactive_cfg(cfg)
    window = window_minutes or int(p.get("evaluationWindowMinutes", 30))
    since = datetime.now() - timedelta(minutes=window)
    events = load_clipboard_events(root, since, None, cfg)
    min_wispr = _wispr_min_chars(cfg)
    # Transcriptions: long text or wispr-nearby
    filtered = [(t, tx, p, w) for t, tx, p, w in events if len(tx) >= min_wispr or w]
    return merge_utterances(filtered, cfg)


def latest_utterance(cfg: dict) -> Utterance | None:
    utterances = recent_transcriptions(cfg, window_minutes=60)
    return utterances[-1] if utterances else None


def latest_transcription_excerpt(cfg: dict, max_len: int = 120) -> str:
    u = latest_utterance(cfg)
    if not u:
        return ""
    one_line = " ".join(u.text.split())[:max_len]
    return one_line
