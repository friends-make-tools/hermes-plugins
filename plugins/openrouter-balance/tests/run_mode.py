"""Single-mode verification server for the openrouter-balance backend.

Env-driven:
  PORT   — port to serve on (required)
  MODE   — success | nokey | e401 | down   (default: success)

Modes:
  success — real key sourcing, real OpenRouter upstream
  nokey   — HERMES_HOME/LOCALAPPDATA point at an empty dir, key var unset
  e401    — OPENROUTER_API_BASE points at the built-in mock that answers 401
  down    — OPENROUTER_API_BASE points at a dead local port

Run:  PORT=49703 MODE=e401 python run_mode.py
"""
import importlib.util
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import fastapi
import uvicorn

HERE = os.path.dirname(os.path.abspath(__file__))
API_FILE = os.path.join(HERE, "..", "dashboard", "plugin_api.py")
PORT = int(os.environ.get("PORT", "49701"))
MODE = os.environ.get("MODE", "success")
# Override so repeat runs can dodge ports still in TIME_WAIT from an earlier rig.
MOCK_PORT = int(os.environ.get("MOCK_PORT", "49799"))

spec = importlib.util.spec_from_file_location("openrouter_balance_plugin_api", API_FILE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class Mock401Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"error": {"message": "Invalid management key"}}).encode()
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if MODE == "e401":
    mod.OPENROUTER_CREDITS_URL = f"http://127.0.0.1:{MOCK_PORT}/credits"
    mod.OPENROUTER_ACTIVITY_URL = f"http://127.0.0.1:{MOCK_PORT}/activity"
    mock = ThreadingHTTPServer(("127.0.0.1", MOCK_PORT), Mock401Handler)
    threading.Thread(target=mock.serve_forever, daemon=True).start()
elif MODE == "down":
    mod.OPENROUTER_CREDITS_URL = "http://127.0.0.1:1/credits"
    mod.OPENROUTER_ACTIVITY_URL = "http://127.0.0.1:1/activity"

app = fastapi.FastAPI()
# Same call the production server makes (web_server.py:19247).
app.include_router(mod.router, prefix="/api/plugins/openrouter-balance")

uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="error")
