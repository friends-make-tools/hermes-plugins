# hermes-plugins

Hermes plugins built for this machine, plus the specs that define them.
The repo keeps one canonical copy of every plugin. The running copies live
under `AppData\Local\hermes\plugins\`.

## Layout

| Path | Contents |
|---|---|
| `plugins/` | One folder per plugin. Each folder installs into `$HERMES_HOME/plugins/<id>/`. |
| `specs/` | Task specs the plugins were built from. |

## Plugins

| Plugin | What it does | Docs |
|---|---|---|
| `openrouter-balance` | Status bar chip: OpenRouter prepaid balance and 30-day spend. | [plugins/openrouter-balance/README.md](plugins/openrouter-balance/README.md) |

## Plugin anatomy

A plugin folder here can carry three parts:

```
plugins/<id>/
├── plugin.yaml          # agent-plugin manifest (backend gate)
├── __init__.py          # agent-side registration (empty when not needed)
├── dashboard/
│   ├── manifest.json    # web-server manifest; "api" names the Python module
│   └── plugin_api.py    # Python backend, mounted at /api/plugins/<id>/
├── desktop/
│   └── plugin.js        # desktop app half (UI; opt-in in Settings → Plugins)
└── tests/               # verification scripts
```

The Python backend mounts only when the plugin id is in `plugins.enabled`
in `config.yaml`. The desktop half loads only when the user toggles the
plugin on in Settings → Plugins. Both gates are required.

## Install / update a plugin

1. Edit the plugin under `plugins/<id>/`.
2. Copy the folder to the Hermes home:

   ```bash
   cp -r plugins/<id> "$LOCALAPPDATA/hermes/plugins/"
   ```

3. Restart the Hermes desktop app (or reload desktop plugins from ⌘K for
   desktop-half changes).

## Specs

Each `specs/*.md` file is the build spec for one plugin: problem, data
sources, locked decisions, requirements, and acceptance criteria. The
plugin README summarizes setup; the spec records why it is built this way.

## Conventions

- Secrets live only in `$HERMES_HOME/.env`. Never in `config.yaml`, never
  in plugin code, never logged.
- Backends use Python 3.11 stdlib only. No new dependencies.
- Desktop files are plain ESM loaded uncompiled. UI uses `jsx()` calls,
  not JSX syntax. Only `@hermes/plugin-sdk`, `react`, and
  `react/jsx-runtime` import successfully.
- Tests keep artifacts out of git (see `.gitignore`).
