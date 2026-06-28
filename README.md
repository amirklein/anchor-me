# Focus Guardian

Portable productivity companion: **Familiar** watches what you do on screen and clipboard (including Wispr dictation); **Focus Guardian** detects sustained drift and chimes in proactively.

Works on any machine where Familiar is installed. Not tied to Cursor, Claude Code, or a specific IDE — use the CLI from Terminal, wire it into Claude Code, or paste `fg coach --print-prompt` into any AI tool.

## Architecture

```
┌─────────────┐     stills + .clipboard.txt   ┌──────────────────┐
│  Familiar   │ ────────────────────────────► │ Focus Guardian   │
│  (sensor)   │   OCR, titles, Wispr text     │  guardian daemon │
└─────────────┘                               └────────┬─────────┘
                                                       │
                    ┌──────────────────────────────────┼──────────────────┐
                    ▼                                  ▼                  ▼
             macOS notification                  drift engine         fg review
             (sustained drift only)              (30m window)         (retrospective)
```

| Layer | Role |
|-------|------|
| **Familiar** | Continuous screen + clipboard on each computer |
| **Guardian** | Event-driven: new Familiar files → debounce → drift check → chime |
| **Review** | Deep retrospective over hours (`fg review`) |

## Philosophy

- **Proactive by default** — `fg guardian start` watches Familiar; you do not run commands to get help.
- **Wispr/clipboard is first-class** — what you dictate is the primary intent signal; screen corroborates.
- **Sustained drift only** — no fixed 15-minute check-ins; chime after ~10 min off-goal + 25 min cooldown.
- **`fg review`** stays for end-of-session retrospectives (hours stitched into work blocks).

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for Familiar fork plans (Zoom audio, etc.).

## Quick start (any computer)

### 1. Prerequisites

- Python 3.10+
- [Familiar](https://familiar.ai) installed, recording enabled
- `~/.familiar/settings.json` present (created by Familiar setup)

### 2. Install Focus Guardian

```bash
git clone <your-repo-url> ~/focus-guardian
cd ~/focus-guardian
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
fg init
```

### 3. Set your goal

```bash
fg profile job_search
fg goal "Ship HiBob MVP slide + working demo" -k hibob,bob-onboard,cursor
```

Config lives at **`~/.focus-guardian/config.json`**. Sync via iCloud or dotfiles if you want the same goals everywhere.

### 4. Run (proactive — recommended)

```bash
fg guardian start          # background daemon
fg guardian status         # one-shot drift evaluation (no notify unless sustained)
fg guardian once           # evaluate + notify if drift sustained
fg review --human          # retrospective: work blocks + Wispr excerpts
fg coach                   # coaching from last review or drift report
fg status
fg guardian stop
```

Opt out of proactive nudges: set `"interventionMode": "manual"` in config.

Legacy interval watch (only if not proactive): `fg watch start -i 45`

## New machine checklist

1. Install Familiar + enable recording  
2. `git clone` this repo (or copy the folder)  
3. `pip install -e .` in a venv  
4. `fg init` && `fg profile job_search`  
5. `fg guardian start`

Optional: auto-start on login (macOS):

```bash
./scripts/install-launchd.sh
```

## Use with Claude Code / Codex / Cursor

**Option A — Proactive notifications**  
`fg guardian start` — macOS alerts when sustained drift is detected.

**Option B — Retrospective**  
`fg review --human` then `fg coach`

**Option C — API coaching**  
```bash
export ANTHROPIC_API_KEY=...
fg review && fg coach --api
```

## Drift signals (live guardian)

| Code | Meaning |
|------|---------|
| `wispr_off_topic` | Dictation off goal for sustained window |
| `topic_pivot` | Latest Wispr pivoted away from assignment keywords |
| `distraction_streak` | LinkedIn, WhatsApp, personal tabs |
| `ai_research_loop` | Long Claude/Gemini without building |
| `polish_without_build` | Slides/Lovable without implementation |
| `wispr_distraction_spike` | Off-topic dictation on distraction surface |

Tune in `config.json` → `proactive` and `thresholds`. See `config.example.json`.

## Config sync across machines

| What | Where | Sync? |
|------|--------|-------|
| Code | `~/focus-guardian` (git) | Yes |
| Goals & rules | `~/.focus-guardian/config.json` | Copy or dotfiles |
| Familiar data | Per-machine `contextFolderPath` | Local only |
| Reports | `~/.focus-guardian/state/` | Ephemeral |

Set `familiarStillsPath` if Familiar uses a custom data path.

## License

MIT
