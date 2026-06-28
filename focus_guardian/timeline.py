"""Build a chronological timeline from Familiar stills + clipboards."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from focus_guardian.familiar import parse_capture_time, read_frontmatter, stills_root


@dataclass
class TimelineEvent:
    ts: datetime
    kind: str  # screen | clipboard | transcription
    app: str
    title: str
    detail: str  # OCR snippet or clipboard / Wispr text


@dataclass
class WorkBlock:
    start: datetime
    end: datetime
    events: list[TimelineEvent]
    dominant_apps: list[tuple[str, int]]
    label: str


def _ocr_preview(md: Path, max_lines: int = 8) -> str:
    lines: list[str] = []
    in_ocr = False
    with md.open(encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.strip() == "# OCR":
                in_ocr = True
                continue
            if in_ocr:
                if line.startswith("#"):
                    break
                m = re.match(r'^- "(.*)"\s*$', line.strip())
                if m:
                    lines.append(m.group(1))
                if len(lines) >= max_lines:
                    break
    return " | ".join(lines[:max_lines])


def _clipboard_max_chars(cfg: dict | None) -> int:
    if not cfg:
        return 400
    p = {**cfg.get("proactive", {}), **cfg}
    return int(p.get("maxClipboardChars", 8000))


def load_timeline(
    root: Path,
    *,
    since: datetime,
    until: datetime | None = None,
    max_events: int = 2000,
    cfg: dict | None = None,
) -> list[TimelineEvent]:
    until = until or datetime.now()
    events: list[TimelineEvent] = []

    for session in root.iterdir():
        if not session.is_dir() or not session.name.startswith("session-"):
            continue
        for path in sorted(session.iterdir()):
            if path.suffix == ".md":
                ts = parse_capture_time(path.stem)
                if ts is None or ts < since or ts > until:
                    continue
                fm = read_frontmatter(path)
                app = fm.get("app", "unknown")
                title = fm.get("window_title_norm", fm.get("window_title_raw", "unknown"))
                events.append(
                    TimelineEvent(
                        ts=ts,
                        kind="screen",
                        app=app,
                        title=title,
                        detail=_ocr_preview(path),
                    )
                )
            elif path.name.endswith(".clipboard.txt"):
                stem = path.name.replace(".clipboard.txt", "")
                ts = parse_capture_time(stem)
                if ts is None or ts < since or ts > until:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore").strip()
                if not text or len(text) < 3:
                    continue
                max_chars = _clipboard_max_chars(cfg)
                min_wispr = int((cfg or {}).get("proactive", {}).get("wisprMinChars", 80))
                kind = "transcription" if len(text) >= min_wispr else "clipboard"
                detail = text[:max_chars]
                if len(text) > max_chars:
                    detail += "…"
                events.append(
                    TimelineEvent(
                        ts=ts,
                        kind=kind,
                        app="wispr" if kind == "transcription" else "clipboard",
                        title=kind,
                        detail=detail,
                    )
                )

    events.sort(key=lambda e: e.ts)
    if len(events) > max_events:
        # Keep most recent
        events = events[-max_events:]
    return events


def stitch_work_blocks(
    events: list[TimelineEvent],
    *,
    gap_minutes: int = 25,
    min_events: int = 3,
) -> list[WorkBlock]:
    if not events:
        return []

    blocks: list[WorkBlock] = []
    current: list[TimelineEvent] = [events[0]]

    for ev in events[1:]:
        gap = (ev.ts - current[-1].ts).total_seconds() / 60
        if gap > gap_minutes:
            if len(current) >= min_events:
                blocks.append(_block_from_events(current))
            current = [ev]
        else:
            current.append(ev)
    if len(current) >= min_events:
        blocks.append(_block_from_events(current))

    return blocks


def _block_from_events(events: list[TimelineEvent]) -> WorkBlock:
    from collections import Counter

    apps = Counter(e.app for e in events if e.kind == "screen")
    top = apps.most_common(3)
    start, end = events[0].ts, events[-1].ts
    duration = int((end - start).total_seconds() / 60)
    titles = [e.title for e in events if e.kind == "screen" and e.title != "unknown"]
    label = _infer_block_label(titles, top, duration)
    return WorkBlock(start=start, end=end, events=events, dominant_apps=top, label=label)


def _infer_block_label(
    titles: list[str], top_apps: list[tuple[str, int]], duration_min: int
) -> str:
    joined = " ".join(titles[-20:]).lower()
    if "zoom" in joined or "microsoft teams" in joined or "meet" in joined:
        return f"Meeting block (~{duration_min}m)"
    if any(a in joined for a in ("google slides", "lovable", "gemini")):
        return f"Assignment / polish block (~{duration_min}m)"
    if any(a[0] in ("Cursor", "Terminal", "Code") for a in top_apps):
        return f"Build block (~{duration_min}m)"
    if "claude" in joined:
        return f"AI chat block (~{duration_min}m)"
    if top_apps:
        return f"{top_apps[0][0]} focus (~{duration_min}m)"
    return f"Work block (~{duration_min}m)"


def timeline_since(cfg: dict, hours: float | None = None) -> list[TimelineEvent]:
    root = stills_root(cfg)
    h = hours if hours is not None else float(cfg.get("lookbackHours", 4))
    since = datetime.now() - timedelta(hours=h)
    return load_timeline(root, since=since, cfg=cfg)


def recent_work_blocks(cfg: dict, hours: float | None = None) -> list[WorkBlock]:
    events = timeline_since(cfg, hours)
    gap = int(cfg.get("workBlockGapMinutes", 25))
    return stitch_work_blocks(events, gap_minutes=gap)
