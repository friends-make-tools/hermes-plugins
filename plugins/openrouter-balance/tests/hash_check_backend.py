"""Verify every deployed plugin_api.py copy matches the repo copy (sha256)."""
import hashlib
import os

repo = r"<REPO>\plugins\openrouter-balance\dashboard\plugin_api.py"
roots = [
    r"<HERMES_HOME>\plugins\openrouter-balance\dashboard\plugin_api.py",
]

base = r"<HERMES_HOME>\profiles"
for name in sorted(os.listdir(base)):
    p = os.path.join(base, name, "plugins", "openrouter-balance", "dashboard", "plugin_api.py")
    if os.path.isfile(p):
        roots.append(p)

with open(repo, "rb") as f:
    repo_hash = hashlib.sha256(f.read()).hexdigest()[:12]

match = 0
differ = []
for p in roots:
    try:
        with open(p, "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest()[:12]
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
