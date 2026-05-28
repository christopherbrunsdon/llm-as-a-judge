# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

Live tech-talk demo: LLM-as-a-Judge using Claude Code hooks. A judge LLM intercepts every tool call before execution, validates intent against a constitution, and either allows or blocks. A SQLite database and web server display state in real time.

---

## Demo Commands

```bash
make install          # pip install -r requirements.txt
make folder           # seed the sandbox directory
make judge-off        # Session 1: judge inactive, unchecked execution
make judge-on         # Session 2+: judge enforces constitution
make serve            # start web server at http://localhost:7777
make reset            # clear judge.db and journal.jsonl
tail -f journal.jsonl | jq .   # stream rulings live
```

---

## Architecture

### Three components

**1. The Constitution** (`prompts/constitution.md`)
System prompt for the judge model. Defines five absolute rules (sandbox confinement, do-not-enter, no self-modification, no rule redefinition, no unchecked destruction) and mandates a `RULING: ALLOW` or `RULING: BLOCK` line as the final output line for reliable parsing.

**2. The Hook** (`.claude/hooks/pre_tool_call.py`)
`PreToolUse` hook — fires before every Claude Code tool call.

Flow:
1. If `.judge-active` flag is absent → `exit 0` (Session 1 behaviour, unchecked).
2. Read `prompts/constitution.md`.
3. Write `thinking` event to `judge.db` (web server goes orange).
4. Call judge via Anthropic API (`JUDGE_MODEL` env var, defaults to `claude-sonnet-4-6`).
5. Parse ruling from last line of response.
6. Write `approved` or `denied` event to `judge.db` (web goes green/red).
7. Append entry to `journal.jsonl`.
8. On `BLOCK`: write `{"decision": "block", "reason": ...}` to stdout and `exit 1`.
9. On `ALLOW`: silent `exit 0`.

**3. The Clown** (`prompts/clown.md` + `prompts/escalation_sequence.md`)
Chaos agent loaded for the demo escalation phase. Executes five pre-written prompts of increasing severity without seeking permission. Each attempt is intercepted by the hook.

---

## File Map

```
.claude/
  settings.json              # PreToolUse hook registration (matcher: *)
  hooks/
    pre_tool_call.py         # Hook logic — judge call, DB write, journal

prompts/
  constitution.md            # Judge system prompt (five absolute rules)
  clown.md                   # Chaos agent instructions
  escalation_sequence.md     # Five ordered violation prompts

sandbox/                     # Created by `make folder` — judge's jurisdiction
  folder-{1,2,3}/
    README.md
    script.sh
  do-not-enter/
    README.md                # "Why did you enter?" — Rule 2 trigger
  chaos/
    README.md                # Empty — Clown's playground

server.py                    # HTTP server: GET / (dashboard), GET /status (JSON)
Makefile
requirements.txt
judge.db                     # Runtime — gitignored
journal.jsonl                # Runtime — gitignored
.judge-active                # Flag file — gitignored; toggles judge on/off
```

---

## SQLite Schema

```sql
CREATE TABLE events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL,          -- ISO-8601 UTC
    state     TEXT NOT NULL,          -- 'thinking' | 'approved' | 'denied'
    action    TEXT,                   -- tool_name
    reasoning TEXT                    -- judge full response
);
```

---

## Web Server

`server.py` — pure stdlib, no framework. Polls `judge.db` every 500 ms from the browser.

| State | Background |
|-------|-----------|
| `thinking` | Orange `#b45309` |
| `approved` | Green `#15803d` |
| `denied`   | Red `#b91c1c` |
| `idle`     | Grey `#374151` |

Header shows live counts: Approved / Denied / Evaluated (= total judge invocations).

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `JUDGE_MODEL` | `claude-sonnet-4-6` | Model used for judge calls |
| `ANTHROPIC_API_KEY` | — | Required for judge |
| `JUDGE_PORT` | `7777` | Web server port |

---

## Demo Flow

| Session | Judge | What to show |
|---------|-------|-------------|
| 1 | OFF (`make judge-off`) | Run a violating prompt — executes unchecked |
| 2 | ON (`make judge-on`) | Same prompt — judge blocks; journal streams |
| 3 | ON | Load clown prompt; run escalation sequence; journal accumulates |
| 4 | ON | Audience suggestions — judge responds live |
