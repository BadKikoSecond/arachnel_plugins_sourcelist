# Official Arachnel plugin source list

Public index of `.arach` plugin packages for the Arachnel launcher.

**Index URL (used by the app):**

```
https://gitlab.com/BadKiko/arachnel-plugins-sourcelist/-/raw/main/plugins.json
```

## Layout

| Path | Purpose |
|------|---------|
| `*.arach` | Latest mirror packages (optional; history can live as GitLab package URLs) |
| `plugins.json` | Generated catalog schema **v2** (CI / local script) |
| `tools/generate_plugins_index.py` | Builds `plugins.json` from packages + keeps `builds[]` history |
| `tools/ingest_plugin_build.py` | Merge one release into `plugins.json` (used by plugin CI) |

## Add a plugin (manual)

1. Put `your-plugin.arach` in the repo root (ZIP with `plugin.json` + library).
2. Push to `main`.
3. CI regenerates `plugins.json` (id, version, sha256, download URL, `builds[]`).

Locally:

```bash
python3 tools/generate_plugins_index.py
git add plugins.json *.arach
git commit -m "Add my-plugin"
git push
```

## Auto-publish from plugin CI

Plugin release pipelines (steamidra / freetp) call `ingest_plugin_build.py` with the package download URL after tagging a release. Set CI variable **`SOURCELIST_PUSH_TOKEN`** on the plugin project (token with `write_repository` on this sourcelist).

```bash
python3 tools/ingest_plugin_build.py \
  --arach /path/plugin.arach \
  --url https://gitlab.com/.../package_files/.../download \
  --min-arachnel 0.1.34 \
  --abi-token v0.1.34a
```

## CI verify

On every push that changes `*.arach` (or verify scripts), GitLab CI:

1. **Linux (`verify:linux`)** — downloads Arachnel AppImage + matching Qt, extracts each `.arach`, loads the native library.
2. **Windows (`verify:windows`)** — loads each plugin DLL against **MinGW** Qt (same kit as Arachnel releases).

Tune `ARACHNEL_VERSION` / `QT_VERSION` in `.gitlab-ci.yml` when bumping launcher releases.

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

## Schema (`plugins.json` v2)

```json
{
  "schemaVersion": 2,
  "updatedAt": "2026-07-28T12:00:00Z",
  "plugins": [
    {
      "id": "steamidra",
      "name": "Steam",
      "version": "0.4.1",
      "apiVersion": 3,
      "url": "https://…/steam.arach",
      "sha256": "…",
      "platforms": ["windows", "linux"],
      "builds": [
        {
          "version": "0.4.7",
          "apiVersion": 4,
          "minArachnel": "0.1.34",
          "maxArachnel": "",
          "url": "https://gitlab.com/…/package_files/…/download",
          "sha256": "…",
          "platforms": ["windows", "linux"],
          "abiToken": "v0.1.34a"
        },
        {
          "version": "0.4.1",
          "apiVersion": 3,
          "minArachnel": "0.0.0",
          "maxArachnel": "",
          "url": "https://…/steam.arach",
          "sha256": "…",
          "platforms": ["windows", "linux"],
          "abiToken": "api=3"
        }
      ]
    }
  ]
}
```

- Arachnel that understands `builds[]` picks the newest build where `minArachnel <= appVersion <= maxArachnel` (empty max = no upper bound) and `apiVersion` is supported.
- Top-level `url` / `version` stay on the newest **API ≤ 3** build so older launchers keep a loadable package.
