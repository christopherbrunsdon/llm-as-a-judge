#!/usr/bin/env python3
"""
Judge status web server.

Polls judge.db and exposes:
  GET /        — dashboard HTML
  GET /status  — JSON { state, counts }

Background colour: green=approved, red=denied, orange=thinking, grey=idle.
"""
import http.server
import json
import os
import sqlite3
import socketserver

DB_PATH = "judge.db"
PORT = int(os.environ.get("JUDGE_PORT", 7777))

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
</style>
</head>
<body class="s-idle">
  <header>
    <h1>LLM&nbsp;&nbsp;Judge</h1>
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
    </div>
  </header>
  <main>
    <div id="state-label">Idle</div>
    <div id="last-action"></div>
  </main>
  <script>
    async function refresh() {
      try {
        const d = await (await fetch('/status')).json();
        document.body.className = 's-' + d.state;
        document.getElementById('state-label').textContent =
          d.state.charAt(0).toUpperCase() + d.state.slice(1);
        document.getElementById('cnt-approved').textContent = d.counts.approved;
        document.getElementById('cnt-denied').textContent   = d.counts.denied;
        document.getElementById('cnt-thinking').textContent = d.counts.thinking;
        document.getElementById('last-action').textContent  = d.last_action || '';
      } catch (_) {}
    }
    setInterval(refresh, 500);
    refresh();
  </script>
</body>
</html>
"""


def get_status() -> dict:
    empty = {"state": "idle", "counts": {"approved": 0, "denied": 0, "thinking": 0}, "last_action": ""}
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
        db.close()
        return {"state": state, "counts": counts, "last_action": last_action or ""}
    except Exception:
        return empty


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # suppress access log noise during demo

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
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"http://localhost:{PORT}")
        httpd.serve_forever()
