#!/usr/bin/env python3
"""
Judge status web server.

Polls judge.db and exposes:
  GET /        — dashboard HTML
  GET /status  — JSON { state, counts }

Background colour: green=approved, red=denied, orange=thinking, grey=idle.
"""
import datetime
import http.server
import json
import mimetypes
import os
import random
import sqlite3
import socketserver

DB_PATH = "judge.db"
PORT = int(os.environ.get("JUDGE_PORT", 7777))

REACTION_GIFS = ["no-01.gif", "no-02.gif", "no-03.gif", "no-04.gif", "no-05.gif"]
_last_gif: str | None = None

HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>LLM Judge</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    transition: background-color 0.35s ease;
  }

  /* State backgrounds */
  body.s-approved { background: #15803d; }
  body.s-denied   { background: #b91c1c; }
  body.s-thinking { background: #b45309; }
  body.s-idle     { background: #374151; }

  header {
    background: rgba(0,0,0,.35);
    color: #fff;
    padding: 1.25rem 2.5rem;
    display: flex;
    align-items: center;
    gap: 3rem;
    backdrop-filter: blur(4px);
  }
  header h1 {
    font-size: .875rem;
    font-weight: 400;
    letter-spacing: .12em;
    text-transform: uppercase;
    white-space: nowrap;
  }

  .counters {
    display: flex;
    gap: 2.5rem;
  }
  .counter {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: .15rem;
  }
  .counter .n {
    font-size: 2.25rem;
    font-weight: 700;
    line-height: 1;
  }
  .counter .l {
    font-size: .625rem;
    text-transform: uppercase;
    letter-spacing: .12em;
    opacity: .75;
  }
  .counter.approved .n { color: #86efac; }
  .counter.denied   .n { color: #fca5a5; }
  .counter.thinking .n { color: #fde68a; }
  .counter.turns    .n { color: #e2e8f0; }

  .judge-badge {
    font-size: .625rem;
    font-weight: 700;
    letter-spacing: .12em;
    text-transform: uppercase;
    padding: .25rem .6rem;
    border-radius: 4px;
    align-self: center;
  }
  .judge-on  { background: #16a34a; color: #fff; }
  .judge-off { background: #6b7280; color: #fff; }

  #clown-indicator {
    margin-left: auto;
    font-size: 2rem;
    line-height: 1;
    align-self: center;
    transition: opacity 0.3s;
  }

  main {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 1rem;
  }
  #state-label {
    font-size: 5rem;
    font-weight: 700;
    color: #fff;
    text-transform: uppercase;
    letter-spacing: .15em;
    text-shadow: 0 4px 16px rgba(0,0,0,.4);
  }
  #last-action {
    font-size: .875rem;
    color: rgba(255,255,255,.6);
    letter-spacing: .06em;
  }

  #reaction {
    height: 200px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  #reaction img {
    max-height: 200px;
    max-width: 60vw;
    object-fit: contain;
    border-radius: 8px;
  }

  #gavels {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: .75rem;
    max-width: 80vw;
    margin-top: .5rem;
  }
  #gavels img {
    width: 72px;
    height: 72px;
    object-fit: contain;
    filter: drop-shadow(0 3px 8px rgba(0,0,0,.5));
  }

  @keyframes gavel-drop {
    0%   { opacity: 0; transform: translateY(-40px) rotate(-20deg); }
    60%  { transform: translateY(6px) rotate(4deg); }
    80%  { transform: translateY(-4px) rotate(-2deg); }
    100% { opacity: 1; transform: translateY(0) rotate(0deg); }
  }
  .gavel-item {
    animation: gavel-drop 0.35s cubic-bezier(.22,.61,.36,1) both;
  }
</style>
</head>
<body class="s-idle">
  <header>
    <h1>LLM&nbsp;&nbsp;Judge</h1>
    <span id="judge-badge" class="judge-badge judge-off">OFF</span>
    <div class="counters">
      <div class="counter approved">
        <span class="n" id="cnt-approved">0</span>
        <span class="l">Approved</span>
      </div>
      <div class="counter denied">
        <span class="n" id="cnt-denied">0</span>
        <span class="l">Denied</span>
      </div>
      <div class="counter thinking">
        <span class="n" id="cnt-thinking">0</span>
        <span class="l">Evaluated</span>
      </div>
      <div class="counter turns">
        <span class="n" id="cnt-turns">0</span>
        <span class="l">Turns</span>
      </div>
    </div>
    <span id="clown-indicator" style="display:none">🤡</span>
  </header>
  <main>
    <div id="reaction"></div>
    <div id="state-label">Idlex</div>
    <div id="last-action"></div>
    <div id="gavels"></div>
  </main>
  <script>
    let prevStreak = 0;
    let prevState  = null;
    let prevTurns  = null;

    const rulingAudio = new Audio('/assets/ruling.mp3');
    const pingAudio   = new Audio('/assets/ping.mp3');
    let audioUnlocked = false;

    // Chrome autoplay policy: unlock both audio elements on first gesture.
    function unlockAudio() {
      if (audioUnlocked) return;
      audioUnlocked = true;
      rulingAudio.play().then(() => rulingAudio.pause()).catch(console.error);
      pingAudio.play().then(() => pingAudio.pause()).catch(console.error);
    }
    ['click', 'keydown', 'touchstart'].forEach(e =>
      document.addEventListener(e, unlockAudio)
    );

    function playRuling() {
      rulingAudio.currentTime = 0;
      rulingAudio.play().catch(console.error);
    }

    function playPing() {
      pingAudio.currentTime = 0;
      pingAudio.play().catch(console.error);
    }

    function updateGavels(streak) {
      const container = document.getElementById('gavels');
      const current = container.children.length;
      if (streak === 0) {
        container.innerHTML = '';
        return;
      }
      for (let i = current; i < streak; i++) {
        const img = document.createElement('img');
        img.src = '/assets/gavel.png';
        img.alt = 'gavel';
        img.className = 'gavel-item';
        img.style.animationDelay = (i * 0.06) + 's';
        container.appendChild(img);
      }
      while (container.children.length > streak) {
        container.removeChild(container.lastChild);
      }
    }

    async function updateReaction(streak) {
      const box = document.getElementById('reaction');
      if (streak < 2) {
        box.innerHTML = '';
        return;
      }
      // Fetch a new gif when streak crosses the threshold, or if the box is empty (e.g. page reload with streak already >=2)
      if (prevStreak < 2 || box.children.length === 0) {
        const r = await (await fetch('/gif')).json();
        const img = document.createElement('img');
        img.src = '/assets/' + r.gif;
        img.alt = 'reaction';
        box.innerHTML = '';
        box.appendChild(img);
      }
    }

    async function refresh() {
      try {
        const d = await (await fetch('/status')).json();
        const streak = d.denied_streak || 0;
        document.body.className = 's-' + d.state;
        document.getElementById('state-label').textContent =
          d.state.charAt(0).toUpperCase() + d.state.slice(1);
        document.getElementById('cnt-approved').textContent = d.counts.approved;
        document.getElementById('cnt-denied').textContent   = d.counts.denied;
        document.getElementById('cnt-thinking').textContent = d.counts.thinking;
        document.getElementById('cnt-turns').textContent    = d.turns;
        document.getElementById('last-action').textContent  = d.last_action || '';

        const badge = document.getElementById('judge-badge');
        badge.textContent = d.judge_active ? 'ON' : 'OFF';
        badge.className = 'judge-badge ' + (d.judge_active ? 'judge-on' : 'judge-off');

        const clown = document.getElementById('clown-indicator');
        clown.style.display = d.clown_active ? 'block' : 'none';

        if (prevTurns !== null && d.turns > prevTurns) playPing();
        if (prevState !== null && prevState !== d.state &&
            (d.state === 'approved' || d.state === 'denied')) {
          playRuling();
        }

        await updateReaction(streak);
        updateGavels(streak);
        prevStreak = streak;
        prevState  = d.state;
        prevTurns  = d.turns;
      } catch (_) {}
    }
    setInterval(refresh, 500);
    refresh();
  </script>
</body>
</html>
"""


def get_status() -> dict:
    empty = {"state": "idle", "counts": {"approved": 0, "denied": 0, "thinking": 0}, "turns": 0, "last_action": "", "judge_active": os.path.exists(".judge-active"), "clown_active": os.path.exists(".clown-active")}
    if not os.path.exists(DB_PATH):
        return empty
    try:
        db = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        row = db.execute("SELECT state, action FROM events ORDER BY id DESC LIMIT 1").fetchone()
        state, last_action = (row[0], row[1]) if row else ("idle", "")
        counts = {}
        for s in ("approved", "denied", "thinking"):
            (counts[s],) = db.execute(
                "SELECT COUNT(*) FROM events WHERE state = ?", (s,)
            ).fetchone()
        try:
            (turns,) = db.execute("SELECT COUNT(*) FROM turns").fetchone()
        except Exception:
            turns = 0
        streak = 0
        for (s,) in db.execute("SELECT state FROM events ORDER BY id DESC"):
            if s == "denied":
                streak += 1
            elif s == "approved":
                break
        db.close()
        return {"state": state, "counts": counts, "turns": turns, "last_action": last_action or "", "denied_streak": streak, "judge_active": os.path.exists(".judge-active"), "clown_active": os.path.exists(".clown-active")}
    except Exception:
        return empty


def record_turn() -> None:
    db = sqlite3.connect(DB_PATH)
    db.execute(
        "CREATE TABLE IF NOT EXISTS turns (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL)"
    )
    db.execute("INSERT INTO turns (ts) VALUES (?)", (datetime.datetime.now(datetime.UTC).isoformat(),))
    db.commit()
    db.close()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # suppress access log noise during demo

    def do_POST(self):
        if self.path == "/turn":
            record_turn()
            self.send_response(204)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == "/status":
            body = json.dumps(get_status()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/":
            body = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/gif":
            global _last_gif
            choices = [g for g in REACTION_GIFS if g != _last_gif]
            picked = random.choice(choices)
            _last_gif = picked
            body = json.dumps({"gif": picked}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/assets/"):
            filename = os.path.basename(self.path)
            asset = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", filename)
            try:
                with open(asset, "rb") as f:
                    body = f.read()
                mime, _ = mimetypes.guess_type(filename)
                self.send_response(200)
                self.send_header("Content-Type", mime or "application/octet-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except FileNotFoundError:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"http://localhost:{PORT}")
        httpd.serve_forever()
