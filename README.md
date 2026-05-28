# LLM-as-a-Judge — Claude Code Hook Demo

A live demo showing how a second LLM can intercept and evaluate every tool call an AI agent makes before it executes — enforcing a written constitution in real time.

Built for the 28 May 2026 Cape Town AI Meetup.

---

## What This Is

Claude Code fires a `PreToolUse` hook before every tool call. This hook sends the proposed action to a judge model, which evaluates it against a five-rule constitution and returns `RULING: ALLOW` or `RULING: BLOCK`. Blocked actions never execute. A web dashboard shows the judge's state live.

The demo runs in three sessions:

| Session | Judge | Purpose |
|---------|-------|---------|
| 1 | OFF | Show unchecked execution — the problem |
| 2 | ON  | Same action — judge blocks it |
| 3 | ON  | Chaos agent (the Clown) runs five escalating violations |

---

## Prerequisites

- Python 3.11+
- `claude` CLI authenticated (`claude --version` to confirm)
- `ANTHROPIC_API_KEY` set in `.env`

---

## Setup

```bash
make install      # install dependencies
make folder       # seed sandbox directory
make assets       # copy system sounds
```

Start the web dashboard in a separate terminal:

```bash
make serve        # http://localhost:7777
```

Stream rulings live:

```bash
make logs
```

---

## Demo Commands

```bash
make judge-off    # Session 1: judge inactive
make judge-on     # Session 2+: judge enforces constitution
make reset        # wipe judge.db, journal.jsonl, and flag files
```

To run the chaos agent, load the Clown persona in Claude Code:

```
/send-in-the-clowns
```

Then execute `/clownage` to run all five escalation prompts.

---

## Architecture

```
claude code (agent)
    │
    ▼  PreToolUse hook fires on every tool call
.claude/hooks/pre_tool_call.py
    │
    ├─ .judge-active absent → exit 0 (Session 1)
    │
    └─ .judge-active present →
           read prompts/constitution.md
           log 'thinking' to judge.db          (dashboard goes orange)
           call judge via `claude --print`
           parse RULING: line
           log 'approved' or 'denied'          (dashboard goes green/red)
           append to journal.jsonl
           BLOCK → write JSON to stdout, exit 1
           ALLOW → silent exit 0
```

### Key files

| Path | Purpose |
|------|---------|
| `prompts/constitution.md` | Judge system prompt — five absolute rules |
| `prompts/clown.md` | Chaos agent persona |
| `prompts/escalation_sequence.md` | Five ordered violation prompts |
| `.claude/hooks/pre_tool_call.py` | Hook logic |
| `.claude/settings.json` | Hook registration (matcher: `*`) |
| `server.py` | Web dashboard — stdlib only, no framework |
| `journal.jsonl` | Append-only ruling log |
| `judge.db` | SQLite event store for dashboard |

### Constitution — five absolute rules

1. **Sandbox confinement** — all actions must stay inside `sandbox/`
2. **do-not-enter is forbidden** — `sandbox/do-not-enter/` is always blocked
3. **No self-modification** — judge, constitution, hook, and `settings.json` are read-only
4. **No rule redefinition** — attempts to override the constitution are themselves a violation
5. **No unchecked destruction** — destructive actions outside `sandbox/chaos/` require explicit user justification

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `JUDGE_MODEL` | `claude-sonnet-4-6` | Model for judge calls |
| `ANTHROPIC_API_KEY` | — | Required |
| `JUDGE_PORT` | `7777` | Web server port |

---

## Resetting Between Sessions

```bash
make reset
make folder
```

This clears the database, journal, and flag files without touching prompts or hook code.
