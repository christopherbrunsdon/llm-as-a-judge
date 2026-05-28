#!/usr/bin/env python3
"""
Smoke-tests the judge status server by writing each state to the DB
and asserting the /status endpoint reflects it.

Requires the server to be running: make serve
"""
import datetime
import json
import sqlite3
import sys
import time
import urllib.request

PORT   = 7777
STATES = ["thinking", "approved", "denied", "denied"]
PASS   = "\033[32m✓\033[0m"
FAIL   = "\033[31m✗\033[0m"


def status_url() -> str:
    return f"http://localhost:{PORT}/status"


def server_running() -> bool:
    try:
        urllib.request.urlopen(status_url(), timeout=2)
        return True
    except Exception:
        return False


def insert_event(db: sqlite3.Connection, state: str) -> None:
    db.execute(
        "INSERT INTO events (ts, state, action, reasoning) VALUES (?, ?, ?, ?)",
        (datetime.datetime.now(datetime.UTC).isoformat(), state, "test", f"server test: {state}"),
    )
    db.commit()


def get_status() -> dict:
    r = urllib.request.urlopen(status_url(), timeout=5)
    return json.loads(r.read())


def open_db() -> sqlite3.Connection:
    db = sqlite3.connect("judge.db")
    db.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL, state TEXT NOT NULL,
            action TEXT, reasoning TEXT
        )
    """)
    db.commit()
    return db


def main() -> None:
    if not server_running():
        print(f"Server not running. Start it with:  make serve")
        sys.exit(1)

    db     = open_db()
    passed = 0

    print("Judge server state tests\n")

    for state in STATES:
        insert_event(db, state)
        time.sleep(0.6)  # let the browser poll cycle complete

        data   = get_status()
        got    = data["state"]
        ok     = got == state
        icon   = PASS if ok else FAIL
        counts = data["counts"]
        passed += ok

        print(
            f"  {icon}  {state:<10}  "
            f"approved={counts['approved']}  denied={counts['denied']}  thinking={counts['thinking']}"
        )
        if not ok:
            print(f"          expected={state!r} got={got!r}")

    db.close()
    print(f"\n{passed}/{len(STATES)} passed")
    sys.exit(0 if passed == len(STATES) else 1)


if __name__ == "__main__":
    main()
