"""Launch all four verification modes as subprocesses, then health-check them.

Usage:  python launch_modes.py check   — spawn, wait, curl each port, print results
       (servers keep running; kill with launch_modes.py stop)
"""
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOGS = HERE / "logs"
MODES = [
    (49701, "success", {}),
    (49702, "nokey", {"HERMES_HOME": str(HERE / "nokey_home"), "LOCALAPPDATA": str(HERE / "nokey_home"), "OPENROUTER_MANAGEMENT_KEY": ""}),
    (49703, "e401", {}),
    (49704, "down", {}),
]

def pids_file():
    return HERE / "server_pids.txt"

def spawn():
    LOGS.mkdir(exist_ok=True)
    (HERE / "nokey_home").mkdir(exist_ok=True)
    pids = []
    for port, mode, extra_env in MODES:
        env = dict(os.environ)
        env.update(extra_env)
        env["PORT"] = str(port)
        env["MODE"] = mode
        log = open(LOGS / f"mode_{mode}.log", "w", encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, str(HERE / "run_mode.py")],
            cwd=str(HERE), env=env, stdout=log, stderr=subprocess.STDOUT,
        )
        pids.append(str(proc.pid))
        print(f"spawned {mode} on {port} pid={proc.pid}")
    pids_file().write_text("\n".join(pids), encoding="utf-8")

def stop():
    if not pids_file().exists():
        print("no pids file")
        return
    for pid in pids_file().read_text().split():
        subprocess.run(["taskkill", "/PID", pid, "/F", "/T"], capture_output=True)
        print(f"killed {pid}")
    pids_file().unlink()

def check():
    import urllib.request, urllib.error
    time.sleep(4)
    results = {}
    for port, mode, _ in MODES:
        url = f"http://127.0.0.1:{port}/api/plugins/openrouter-balance/summary"
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                results[mode] = (r.status, r.read().decode())
        except urllib.error.HTTPError as e:
            results[mode] = (e.code, e.read().decode())
        except Exception as e:
            results[mode] = (0, f"{type(e).__name__}: {e}")
    for mode, (code, body) in results.items():
        print(f"== {mode}: HTTP {code}")
        print(body[:400])
    return results

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "spawn"
    if cmd == "spawn":
        spawn()
    elif cmd == "stop":
        stop()
    elif cmd == "check":
        check()
