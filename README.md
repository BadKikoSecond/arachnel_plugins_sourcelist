# Official Arachnel plugin source list

Public index of `.arach` plugin packages for the Arachnel launcher.

**Index URL (used by the app):**

```
https://raw.githubusercontent.com/BadKikoSecond/arachnel_plugins_sourcelist/main/plugins.json
```

## Layout

| Path | Purpose |
|------|---------|
| `*.arach` | Latest mirror packages (optional legacy mirrors; builds live in the plugins' GitHub Releases) |
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

## Auto-publish from plugin releases

No secret is needed. [`.github/workflows/sourcelist.yml`](.github/workflows/sourcelist.yml) runs every 30 minutes and on demand:

1. **detect** - lists the public Releases of the repos in [`tools/plugin_sources.json`](tools/plugin_sources.json) and downloads those that are not in `plugins.json` yet (stable, semver-tagged, containing the expected `.arach` asset);
2. **verify** - loads each new package's native library against the Arachnel AppImage runtime;
3. **publish** - merges the package into `plugins.json` with `tools/ingest_plugin_build.py` and pushes to `main`.

A plugin release workflow can make this instant with a `repository_dispatch` (event type `plugin-release`, payload `url`, `arach`, `tag`, `min_arachnel`, `max_arachnel`, `abi_token`); it needs a token with *Contents: write* on this repo. By hand: **Actions -> Sources -> Run workflow** (tick *force_latest* to re-check the newest release, or give an explicit package URL).

Manual ingest of a local package:

```bash
python3 tools/ingest_plugin_build.py \
  --arach /path/plugin.arach \
  --url https://github.com/<owner>/<repo>/releases/download/<tag>/plugin.arach \
  --min-arachnel 0.1.34 \
  --abi-token develop
```

## CI verify

[`sources.yml`](.github/workflows/sourcelist.yml) runs `tools/ci/verify-linux.sh` on every package before it is published: it downloads the Arachnel AppImage + matching Qt and loads the plugin library. `tools/ci/verify-windows.ps1` does the same with MinGW Qt on Windows (run it by hand when needed).

Tune `ARACHNEL_VERSION` / `QT_VERSION` (defaults in `tools/ci/verify-linux.sh`) when bumping launcher releases.

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
          "url": "https://github.com/<owner>/<repo>/releases/download/<tag>/<plugin>.arach",
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
