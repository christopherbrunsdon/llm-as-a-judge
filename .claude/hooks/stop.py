#!/usr/bin/env python3
"""
Stop hook — fires when Claude finishes a response turn.

1. Plays assets/ping.aiff (falls back to macOS system sound).
2. POSTs to the judge server to record the turn.
"""
import os
import subprocess
import sys
import urllib.request

ASSET    = "assets/ping.aiff"
FALLBACK = "/System/Library/Sounds/Ping.aiff"
PORT     = int(os.environ.get("JUDGE_PORT", 7777))


def play_ping() -> None:
    sound = ASSET if os.path.exists(ASSET) else FALLBACK
    try:
        subprocess.run(["afplay", sound], timeout=5, check=False)
    except Exception:
        pass


def notify_server() -> None:
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                f"http://localhost:{PORT}/turn",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=2,
        )
    except Exception:
        pass  # server may not be running — non-fatal


if __name__ == "__main__":
    play_ping()
    notify_server()
