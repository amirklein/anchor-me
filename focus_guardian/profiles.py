"""Life-stage / mode profiles — merge into user config."""

from __future__ import annotations

PROFILES: dict[str, dict] = {
    "job_search": {
        "description": "Unemployed; optimize time on take-home assignments and interview prep.",
        "currentGoal": "Convert assignment time into interview offers: sharp thesis, proof, not endless polish.",
        "goalKeywords": [
            "assignment",
            "slides",
            "interview",
            "hibob",
            "aligned",
            "sympera",
            "lovable",
            "cursor",
            "deel",
        ],
        "assignmentKeywords": [
            "hibob",
            "bob-onboard",
            "sympera",
            "deel",
            "take-home",
            "mvp",
        ],
        "lookbackHours": 6,
        "interventionMode": "proactive",
        "watchIntervalMinutes": 0,
        "proactive": {
            "pollSeconds": 90,
            "debounceSeconds": 60,
            "evaluationWindowMinutes": 30,
            "driftSustainedMinutes": 10,
            "wisprMinChars": 80,
            "maxClipboardChars": 8000,
            "chimeCooldownMinutes": 25,
        },
        "thresholds": {
            "distractionMinutes": 20,
            "contextSwitchesPerWindow": 18,
            "aiLoopMinutes": 35,
            "slidesWithoutBuildMinutes": 45,
        },
        "distractionTitlePatterns": [
            "linkedin",
            "relationship",
            "whatsapp",
            "feed |",
            "top job picks",
            "etrade",
            "stock plan",
            "youtube",
            "maccabi",
        ],
        "successSignals": [
            "time on assignment brief + deliverable",
            "submitted or rehearsed narrative",
            "mock interview / recruiter call",
        ],
        "antiPatterns": [
            "gemini critique loop without editing deck",
            "new research after thesis is clear",
            "meta tooling during active deadline",
        ],
    },
    "employed": {
        "description": "In role; align daily work to weekly outcomes and career milestones.",
        "currentGoal": "Set your weekly outcome in config.",
        "goalKeywords": [],
        "lookbackHours": 8,
        "interventionMode": "manual",
        "watchIntervalMinutes": 0,
        "thresholds": {
            "distractionMinutes": 15,
            "contextSwitchesPerWindow": 15,
            "aiLoopMinutes": 25,
            "slidesWithoutBuildMinutes": 30,
        },
        "successSignals": [
            "progress on stated weekly milestone",
            "shipped increment toward team goal",
        ],
        "antiPatterns": [
            "slack/email without returning to milestone",
            "polish before core deliverable",
        ],
    },
}


def apply_profile(cfg: dict, profile_name: str) -> dict:
    base = dict(cfg)
    prof = PROFILES.get(profile_name)
    if not prof:
        raise ValueError(f"Unknown profile: {profile_name}. Choose: {', '.join(PROFILES)}")
    merged = {**base, **prof, "activeProfile": profile_name}
    th = {**base.get("thresholds", {}), **prof.get("thresholds", {})}
    merged["thresholds"] = th
    if "proactive" in base or "proactive" in prof:
        merged["proactive"] = {**base.get("proactive", {}), **prof.get("proactive", {})}
    return merged


def list_profiles() -> list[str]:
    return list(PROFILES.keys())
