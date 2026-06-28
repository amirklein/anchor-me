"""Read Familiar stills from the local machine."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path


def familiar_settings_path() -> Path:
    return Path.home() / ".familiar" / "settings.json"


def stills_root(cfg: dict | None = None) -> Path:
    override = (cfg or {}).get("familiarStillsPath")
    if override:
        p = Path(override).expanduser()
        if p.is_dir():
            return p
        raise FileNotFoundError(f"familiarStillsPath not found: {p}")

    settings = familiar_settings_path()
    if not settings.exists():
        raise FileNotFoundError(
            "Familiar not configured on this machine. Install Familiar and set "
            "~/.familiar/settings.json, or set familiarStillsPath in config."
        )
    data = json.loads(settings.read_text(encoding="utf-8"))
    root = Path(data["contextFolderPath"]) / "familiar" / "stills-markdown"
    if not root.is_dir():
        raise FileNotFoundError(f"Familiar stills directory missing: {root}")
    return root


def parse_capture_time(stem: str) -> datetime | None:
    m = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})-(\d+)", stem)
    if not m:
        return None
    d, hh, mm, ss, _ = m.groups()
    return datetime.fromisoformat(f"{d}T{hh}:{mm}:{ss}")


def read_frontmatter(md: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    with md.open(encoding="utf-8", errors="ignore") as f:
        if f.readline().strip() != "---":
            return out
        for line in f:
            if line.strip() == "---":
                break
            if ": " in line:
                k, v = line.split(": ", 1)
                out[k.strip()] = v.strip()
    return out
