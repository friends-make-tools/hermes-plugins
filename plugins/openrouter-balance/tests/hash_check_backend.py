"""Verify every deployed plugin_api.py copy matches the repo copy (sha256).

Paths are derived, not hardcoded: the repo copy is located relative to this
file, and deployed copies are resolved from $HERMES_HOME (default
~/.hermes), scanning profiles/ when present.
"""
import hashlib
import os
from pathlib import Path

REPO_FILE = Path(__file__).resolve().parents[1] / "dashboard" / "plugin_api.py"


def first_existing_home() -> Path:
    """Generic Hermes-home resolution: $HERMES_HOME, then the two defaults."""
    env_home = os.environ.get("HERMES_HOME")
    candidates = []
    if env_home:
        candidates.append(Path(env_home))
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "hermes")
    candidates.append(Path.home() / ".hermes")
    for c in candidates:
        if c.is_dir():
            return c
    return candidates[-1]


hermes_home = first_existing_home()
roots = [
    hermes_home / "plugins" / "openrouter-balance" / "dashboard" / "plugin_api.py"
]

profiles_dir = hermes_home / "profiles"
if profiles_dir.is_dir():
    for name in sorted(os.listdir(profiles_dir)):
        p = profiles_dir / name / "plugins" / "openrouter-balance" / "dashboard" / "plugin_api.py"
        if p.is_file():
            roots.append(p)


def sha12(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


repo_hash = sha12(REPO_FILE)

match = 0
differ = []
for p in roots:
    try:
        h = sha12(p)
    except OSError:
        continue
    if h == repo_hash:
        match += 1
    else:
        differ.append((p, h))

print(f"repo sha256[:12]={repo_hash}")
print(f"identical copies: {match}/{len(roots)}")
for p, h in differ:
    print(f"DIFFERS {h}: {p}")
