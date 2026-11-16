---
title: Desktop Client
description: Tauri 2 + PyInstaller sidecar desktop app — installers, modes, and packaging
---

# Desktop Client

## Architecture

The desktop app has two layers:

- **Tauri 2 shell**: reuses the same `frontend/` React code from this repo,
  with cross-platform windows and system tray
- **backend sidecar**: the local `backend` (FastAPI + axon-quant) packaged by
  PyInstaller into a single-file binary, started and stopped automatically
  with the desktop app

```
QuantCell.app
├── Tauri shell (React frontend)
└── quantcell-backend (sidecar binary, PyInstaller onefile)
        └── bundled FastAPI + axon-quant + DuckDB
```

## Run modes

| Mode | Description |
|------|-------------|
| `local` | uses the bundled sidecar backend, no login, all data local |
| `remote` | connects to a remote QuantCell server (team / cloud deployments) |

## Installers

| Platform | Architecture | Package |
|----------|--------------|---------|
| macOS (Apple Silicon) | aarch64 | `QuantCell_<ver>_aarch64.dmg` |
| macOS (Intel) | x86_64 | `QuantCell_<ver>_x64.dmg` |
| Windows | x86_64 | `QuantCell_<ver>_x64.msi` / `.exe` |
| Linux | x86_64 | `quantcell_<ver>_amd64.deb` / `.AppImage` |

**Download location**: GitHub Actions artifacts (`quantcell-desktop-*`),
generated automatically on `v*` tags.

**Unsigned binary prompts**:

- macOS first launch: right-click → Open
- Windows: click "Run anyway" when prompted about an unknown publisher

## Local development

```bash
make desktop-build   # Tauri release build (builds the frontend first)
make desktop-run     # open the .app
make desktop         # clean → build → run (most common)
make desktop-kill    # stop leftover desktop processes
make desktop-clean   # kill + clear Rust target + frontend cache
```

Desktop development requires the Rust toolchain (Tauri 2). Full details in
[desktop/README.md](https://github.com/pengwow/quantcell/blob/main/desktop/README.md).

Build internals (sidecar packaging, externalBin wiring) are driven by:

- `desktop/scripts/build-backend.sh` — PyInstaller packaging of the backend
- `desktop/src-tauri/tauri.conf.json` — sidecar declaration and bundle config
- `.github/workflows/desktop-build.yml` — CI packaging (workflow_dispatch / v* tags)
