#!/usr/bin/env python3
"""
LLM-as-a-Judge — PreToolUse hook.

Intercepts every Claude Code tool call. If .judge-active flag exists,
calls the judge via `claude --print` (uses existing Claude Code login),
logs state to SQLite and journal.jsonl, and returns allow or block.
"""
import json
import os
import sys
import sqlite3
import datetime
import subprocess

# Paths resolved from repo root (cwd when hook runs)
JUDGE_FLAG    = ".judge-active"
CONSTITUTION  = "prompts/constitution.md"
DB_PATH       = "judge.db"
JOURNAL_PATH  = "journal.jsonl"
JUDGE_MODEL   = os.environ.get("JUDGE_MODEL", "claude-sonnet-4-6")


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
        (datetime.datetime.now(datetime.UTC).isoformat(), state, action, reasoning),
    )
    db.commit()


# ── Audit Logging ─────────────────────────────────────────────────────────────

def audit_log(level: str, message: str, metadata: dict) -> None:
    """Emit one structured JSON audit line to stderr.

    stdout is reserved for the Claude Code hook control protocol
    ({"decision": "block", ...}). Docker captures stderr into the same
    container log stream, so Grafana Alloy ships these lines to Loki
    identically to stdout lines.
    """
    entry = {
        "level":     level,
        "time":      datetime.datetime.now(datetime.UTC).isoformat(),
        "component": "audit",
        "message":   message,
        "metadata":  metadata,
    }
    sys.stderr.write(json.dumps(entry) + "\n")
    sys.stderr.flush()


# ── Journal ───────────────────────────────────────────────────────────────────

def append_journal(entry: dict) -> None:
    with open(JOURNAL_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ── Judge ─────────────────────────────────────────────────────────────────────

def call_judge(constitution: str, tool_name: str, tool_input: dict) -> str:
    """Invoke judge via `claude --print`. Inherits Claude Code OAuth session."""
    action_block = (
        f"Tool: {tool_name}\n"
        f"Parameters:\n```json\n{json.dumps(tool_input, indent=2)}\n```"
    )
    prompt = (
        "You are the Judge. Apply the following constitution strictly:\n\n"
        f"<constitution>\n{constitution}\n</constitution>\n\n"
        "Evaluate this proposed action and return your ruling:\n\n"
        + action_block
    )
    # JUDGE_SUBPROCESS=1 prevents the claude subprocess from re-entering this hook.
    # Prompt passed via stdin to avoid CLI argument length limits on long tool payloads.
    child_env = {**os.environ, "JUDGE_SUBPROCESS": "1"}
    result = subprocess.run(
        ["claude", "--print", "--model", JUDGE_MODEL],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=60,
        env=child_env,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"exit {result.returncode}")
    return result.stdout.strip()


def parse_ruling(text: str) -> str:
    """Return 'BLOCK' or 'ALLOW'. Matches only the final RULING: line; fails closed."""
    for line in reversed(text.splitlines()):
        stripped = line.strip().upper()
        if stripped.startswith("RULING:"):
            return "BLOCK" if "BLOCK" in stripped else "ALLOW"
    sys.stderr.write("[judge] WARNING: no RULING: line in response — defaulting to BLOCK\n")
    return "BLOCK"


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    # Recursion guard: if we are already inside a judge subprocess, allow immediately
    if os.environ.get("JUDGE_SUBPROCESS"):
        sys.exit(0)

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
    audit_log("info", "Judge evaluating tool call", {"tool": tool_name, "input": tool_input})

    try:
        response = call_judge(constitution, tool_name, tool_input)
    except Exception as exc:
        audit_log("warn", "Judge unavailable — failing closed", {"tool": tool_name, "error": str(exc)})
        log_event(db, "denied", tool_name, f"Judge error (fail closed): {exc}")
        db.close()
        print(json.dumps({"decision": "block", "reason": f"Judge unavailable: {exc}"}))
        sys.exit(1)

    ruling = parse_ruling(response)
    state  = "approved" if ruling == "ALLOW" else "denied"
    log_event(db, state, tool_name, response)
    db.close()

    append_journal({
        "ts":        datetime.datetime.now(datetime.UTC).isoformat(),
        "action":    tool_name,
        "params":    tool_input,
        "ruling":    ruling,
        "reasoning": response,
    })

    if ruling == "BLOCK":
        audit_log("critical", "Tool call blocked by judge", {"tool": tool_name, "ruling": "BLOCK"})
        print(json.dumps({"decision": "block", "reason": response}))
        sys.exit(1)

    audit_log("info", "Tool call allowed by judge", {"tool": tool_name, "ruling": "ALLOW"})
    # ALLOW: silent exit 0


if __name__ == "__main__":
    main()
