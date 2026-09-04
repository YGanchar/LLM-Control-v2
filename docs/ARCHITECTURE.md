# LLM-Control v2 — Architecture & Developer Guide

> English version: this file. Русская версия: [ARCHITECTURE_RU.md](ARCHITECTURE_RU.md)

## 1. What it is

**LLM-Control v2** is a lightweight GUI control panel for `llama-server` instances running on a remote GPU machine. It is a **thin client**: the app never runs inference or loads models itself. It writes config files, drives systemd services via `llmctl` over SSH, and collects metrics from `/proc` and `nvidia-smi`.

Typical setup: a silent workstation plus a headless GPU server in the corner. The panel lives on the workstation, inference stays on the server, and the engine is stock `llama-server` from llama.cpp.

```
WORKSTATION (client)                          GPU SERVER (headless)
┌─────────────────────────────┐               ┌────────────────────────────────┐
│ LLM-Control-v2 (PySide6)    │               │ llama-server :8080 (systemd)   │
│                             │               │ llama-server :8081 (systemd)   │
│ QProcess + ssh ─────────────┼── sudo ───────┼► /usr/local/bin/llmctl         │
│                             │               │   └─ systemctl {start|stop|    │
│ RemoteMonitorThread ────────┼── SSH ────────┼► /proc, nvidia-smi, pgrep      │
│ (paramiko, 2 s poll)        │               │                                │
│                             │               │ /srv/storage/llama-mode.conf   │
│ /media/rtx-storage/*.conf ◄─┼─── NFS ───────┼─ (read by systemd units)       │
│ ~/.ssh/id_ed25519_llm       │               │ WoL: Magic Packet UDP:9        │
└─────────────────────────────┘               └────────────────────────────────┘
```

## 2. Module map

| Module | Responsibility |
|---|---|
| `main.py` | Entry point: `.env` resolution (external takes priority over the bundled one), logging, SIGTERM/SIGINT → graceful quit |
| `main_ui.py` | `MainWindow`: three tabs, status bar, monitor signal wiring, `retranslate_ui`, `closeEvent` (stops the log stream and the monitor thread) |
| `scanner_widget.py` | `.gguf` scanner: recursive walk, table (name/size/vision), language switcher, `WrappingBar` (custom flow layout) |
| `config_widget.py` | `.mod` presets: MODS directory scan, preset matching by filename prefix, auto-config generator (CTX/BATCH/NGL tables by quant and size) |
| `server_widget.py` | Server panel: 8080/8081 radio, `llmctl` actions via QProcess+ssh, config editor with validator, WoL/poweroff, `journalctl -f` streaming |
| `locale_manager.py` | `LocaleManager` (the `locale` singleton): JSON dictionaries, fallback to `en` |
| `services/system_monitor.py` | `RemoteMonitorThread` (QThread + paramiko): CPU/RAM/GPU/VRAM, process-to-port mapping, self-healing, WoL, `poweroff` |
| `services/ssh_manager.py` | SSH key discovery and caching, argument builder for the external `ssh` client |
| `services/ssh_setup.py` | First-run helpers: `ssh-keygen`, `ssh-copy-id`, sudoers instructions |
| `services/model_scanner.py` | Iterative file-by-extension finder (`os.scandir`, no recursion) |
| `services/mod_generator.py` | Standalone CLI utility (not used by the GUI): client path → server `/srv/models/...` mapping |
| `services/server_control.py` | Empty import-compatibility stub |

## 3. Threading and data flow

**GUI thread** — all widgets. Disk scanning runs synchronously on this thread (a deliberate simplification, see "Known limitations").

**RemoteMonitorThread (QThread)** — a 2-second poll loop:
1. `cat /proc/stat` → CPU (delta between polls), `cat /proc/meminfo` → RAM;
2. `pgrep -af llama-server` + parsing `--port` from cmdline → which instances are alive, which PID owns which port;
3. `nvidia-smi --query-gpu=...` → per-card VRAM/power;
4. `nvidia-smi --query-compute-apps=...` → per-PID VRAM → attributed to instance ports.

Self-healing: 3 consecutive failures → forced reconnect; SSH keepalive every 10 s; the `planned_shutdown` flag silences noise after an intentional `poweroff`. Shutdown: `stop()` from `closeEvent`, `wait(3000)` → `terminate()`.

**Control actions** — one QProcess per action: `ssh -i <key> <host> sudo /usr/local/bin/llmctl <action>[ 8081]`. Output is appended to the log pane via `readyReadStandardOutput/StandardError`. The log stream (`journalctl -f`) is kept in `current_stream_process` and terminated before a new action and on window close.

**Signals (Qt)**: `metrics_received` (monitor → status bar), `scan_started/scan_finished/model_selected` (scanner → main_ui → config), `run_command_requested` (config → server panel), `language_changed` (scanner → `retranslate_ui`), `shutdown_status_received/wol_status_received` (monitor → log pane).

## 4. Configuration files

| File | Purpose |
|---|---|
| `.env` (next to the binary/script) | All settings: paths, SSH, MAC, language, window width, last selections. Full list — `.env.example` |
| `.env` bundled into the build | Fallback when the external one is missing (see §5) |
| `model_layers.json` | Model name → layer count (caps NGL in the auto generator) |
| `locales/{ru,en,es}.json` | Flat key → string dictionaries. Key sets must stay identical across languages |
| `*.mod` (MODS directory) | Launch presets in dotenv style: `MODEL/HOST/PORT/THREADS/CTX/BATCH/NGL/EXTRA`; multi-line `EXTRA` with `\` is supported |
| `llama-mode.conf` / `llama-mode-8081.conf` | Working server configs. Written by the panel to the NFS path `/media/rtx-storage/` (server-side `/srv/storage/`), read by the systemd units at `llama-server` start |

## 5. `.env` resolution rules (the contract)

- **From source**: `.env` next to `main.py`.
- **Frozen (PyInstaller onefile)**: the `.env` **next to the binary** wins; the bundled one (`_MEIPASS/.env`) is used only if the external file is missing.
- Why: `load_dotenv` by default does **not override** already-set variables, so load order matters. `main.py` loads the external file first; `__file__` in a frozen build points inside `_MEIPASS` and must not be used to locate the external `.env`.

## 6. Localization

- `LocaleManager.translate(key)` returns the string for a key; a missing key returns the key itself (no fallback dictionary). Rule: **add a key to all three JSON files at once**.
- Every widget implements `retranslate()`; `MainWindow.retranslate_ui()` fans it out across tabs and the status bar (latest metrics are re-applied on top of placeholders).
- Stable geometry: `_sync_stable_sizes()` in the scanner takes the maximum `sizeHint` across all locales (`_all_locale_texts`) — switching language never shifts the layout.
- Adding a language: create `locales/xx.json` with all keys + a `("xx", "config.lang_xx")` pair in `_populate_language_combo` (scanner_widget.py).

## 7. Config validator (`server_widget._validate_config`)

Checks before a config is written to NFS: required keys (`MODEL/PORT/CTX/NGL`), PORT range, CTX ≥ 8, NGL > 0 or `auto`, missing space before `\` in a multi-line `EXTRA` (arguments would glue together), and the `NGL="auto"` + manual `--tensor-split` combination — known to OOM at startup. `INFO:` lines are stripped on save.

## 8. Build and deployment

```bash
# environment
python -m venv .venv
.venv/bin/pip install -r requirements.txt

# checks
.venv/bin/python -m py_compile main.py main_ui.py scanner_widget.py \
    config_widget.py server_widget.py locale_manager.py services/*.py

# onefile build (bundles locales/, model_layers.json, .env)
.venv/bin/pyinstaller --noconfirm LLM-Control-v2.spec
# result: dist/LLM-Control-v2

# deploy: copy the binary into the app directory, keep .env next to it
cp dist/LLM-Control-v2 /path/to/appdir/
```

Server side (`server/`): `llmctl` → `/usr/local/bin/llmctl`; `/etc/sudoers.d/llmctl` granting `NOPASSWD` for `llmctl`; units `llama-server.service` (autostart, port 8080) and `llama-server-8081.service`. Details — `docs/DEPLOYMENT.md`.

## 9. Headless smoke test

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python - <<'PY'
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
app = QApplication(sys.argv)
from main_ui import MainWindow
w = MainWindow(); w.show()
QTimer.singleShot(1500, w.close)   # closeEvent: stream + monitor
sys.exit(app.exec())
PY
```

For a frozen binary — same, plus check the log for `.env loaded from <binary dir>/.env` (not `_MEI...`).

## 10. Code conventions

- `_resolve_env_path()` is deliberately repeated in every UI module (the same frozen/script contract) — never replace it with a relative `".env"`.
- User-facing strings only via `locale.translate('key.subkey')`; a hardcoded string is a bug.
- Widgets talk through signals, not upward direct references (the exception is `parent_widget` for dialogs).
- Background shutdown: the log stream and the monitor are stopped in `MainWindow.closeEvent`; QProcess does not kill its child process — only an explicit `terminate()` does.
- Log prefixes: `[MAIN]`, `[MAIN_UI]`, `[SW]`, `[CW]`, `[Monitor]`, `[SSHManager]`, `[LOCALE]`.

## 11. Known limitations

- Scanning (`/media/rtx-models`, the MODS directory) is synchronous on the GUI thread: large/NFS directories freeze the window (marked in code; a QThread candidate).
- The client is Linux-only; remote control uses the system `ssh` client and `paramiko`.
- A personal/LAN tool: authentication is SSH keys only, the panel exposes no HTTP endpoints.
- The NGL/CTX auto-pick tables assume a single GPU; multi-GPU configs are edited by hand.
