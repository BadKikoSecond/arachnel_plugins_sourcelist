# Official Arachnel plugin source list

Public index of `.arach` plugin packages for the Arachnel launcher.

**Index URL (used by the app):**

```
https://gitlab.com/BadKiko/arachnel-plugins-sourcelist/-/raw/main/plugins.json
```

## Layout

| Path | Purpose |
|------|---------|
| `*.arach` | Plugin packages (commit these) |
| `plugins.json` | Generated catalog (CI / local script) |
| `tools/generate_plugins_index.py` | Builds `plugins.json` from packages |

## Add a plugin

1. Put `your-plugin.arach` in the repo root (ZIP with `plugin.json` + library).
2. Push to `main`.
3. CI regenerates `plugins.json` (id, version, sha256, download URL).

Locally:

```bash
python3 tools/generate_plugins_index.py
git add plugins.json *.arach
git commit -m "Add my-plugin"
git push
```

## CI verify

On every push that changes `*.arach` (or verify scripts), GitLab CI:

1. **Linux (`verify:linux`)** — downloads Arachnel AppImage + Qt 6.8.2, extracts each `.arach`, runs `ldd` and loads the native library (same checks as the launcher).
2. **Windows (`verify:windows`)** — loads each plugin DLL against the MSVC Qt runtime.

Only packages that pass both stages should be committed to `main`. Tune `ARACHNEL_VERSION` / `QT_VERSION` in `.gitlab-ci.yml` when bumping launcher releases.

Local check:

```bash
bash tools/ci/verify-linux.sh
# Windows:
pwsh -File tools/ci/verify-windows.ps1
```

## CI note

For auto-commit of `plugins.json`, enable job-token push:

**Settings → CI/CD → Job token permissions → Allow CI job tokens to push to this repository**

Or set CI/CD variable `GIT_PUSH_TOKEN` (Project Access Token with `write_repository`).

## Schema (`plugins.json`)

```json
{
  "schemaVersion": 1,
  "updatedAt": "2026-07-16T12:00:00Z",
  "plugins": [
    {
      "id": "freetp",
      "name": "FreeTP",
      "description": "…",
      "version": "1.0.0",
      "apiVersion": 2,
      "url": "https://gitlab.com/…/raw/main/freetp.arach",
      "sha256": "…",
      "platforms": ["windows", "linux"]
    }
  ]
}
```
