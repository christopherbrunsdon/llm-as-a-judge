#!/usr/bin/env python3
"""
LLM-as-a-Judge — PreToolUse hook.

Intercepts every Claude Code tool call. If .judge-active flag exists,
calls the judge model with the constitution, logs state to SQLite and
journal.jsonl, and returns allow or block to Claude Code.
"""
import json
import os
import sys
import sqlite3
import datetime

# Paths resolved from repo root (cwd when hook runs)
JUDGE_FLAG       = ".judge-active"
CONSTITUTION     = "prompts/constitution.md"
DB_PATH          = "judge.db"
JOURNAL_PATH     = "journal.jsonl"
JUDGE_MODEL      = os.environ.get("JUDGE_MODEL", "claude-sonnet-4-6")


# ── Database ──────────────────────────────────────────────────────────────────

def open_db() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT    NOT NULL,
            state     TEXT    NOT NULL,
            action    TEXT,
            reasoning TEXT
        )
    """)
    db.commit()
    return db


def log_event(db: sqlite3.Connection, state: str, action: str, reasoning: str = "") -> None:
    db.execute(
        "INSERT INTO events (ts, state, action, reasoning) VALUES (?, ?, ?, ?)",
        (datetime.datetime.utcnow().isoformat(), state, action, reasoning),
    )
    db.commit()


# ── Journal ───────────────────────────────────────────────────────────────────

def append_journal(entry: dict) -> None:
    with open(JOURNAL_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ── Judge ─────────────────────────────────────────────────────────────────────

def call_judge(constitution: str, tool_name: str, tool_input: dict) -> str:
    import anthropic  # deferred so missing package only fails when judge is active

    client = anthropic.Anthropic()
    action_block = (
        f"Tool: {tool_name}\n"
        f"Parameters:\n```json\n{json.dumps(tool_input, indent=2)}\n```"
    )
    msg = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=512,
        system=constitution,
        messages=[
            {
                "role": "user",
                "content": (
                    "Evaluate the following proposed action and return your ruling.\n\n"
                    + action_block
                ),
            }
        ],
    )
    return msg.content[0].text


def parse_ruling(text: str) -> str:
    """Return 'BLOCK' or 'ALLOW'. Searches for 'RULING: BLOCK/ALLOW' first."""
    for line in reversed(text.splitlines()):
        line = line.strip().upper()
        if line.startswith("RULING:"):
            return "BLOCK" if "BLOCK" in line else "ALLOW"
    # Fallback keyword scan
    upper = text.upper()
    if "BLOCK" in upper:
        return "BLOCK"
    return "ALLOW"


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name  = payload.get("tool_name", "unknown")
    tool_input = payload.get("tool_input", {})

    # Session 1 behaviour: judge flag absent → allow everything silently
    if not os.path.exists(JUDGE_FLAG):
        sys.exit(0)

    try:
        with open(CONSTITUTION) as f:
            constitution = f.read()
    except FileNotFoundError:
        sys.exit(0)

    db = open_db()
    log_event(db, "thinking", tool_name)

    try:
        response = call_judge(constitution, tool_name, tool_input)
    except Exception as exc:
        log_event(db, "approved", tool_name, f"Judge unavailable: {exc}")
        db.close()
        sys.exit(0)

    ruling = parse_ruling(response)
    state  = "approved" if ruling == "ALLOW" else "denied"
    log_event(db, state, tool_name, response)
    db.close()

    append_journal({
        "ts":       datetime.datetime.utcnow().isoformat(),
        "action":   tool_name,
        "params":   tool_input,
        "ruling":   ruling,
        "reasoning": response,
    })

    if ruling == "BLOCK":
        print(json.dumps({"decision": "block", "reason": response}))
        sys.exit(1)
    # ALLOW: silent exit 0


if __name__ == "__main__":
    main()
