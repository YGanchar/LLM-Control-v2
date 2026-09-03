# Deploying the LLM-Control system (server + client)

This guide describes the full deployment of the LLM-Control system: preparing the
server (`rtx`) and setting up the client (the GUI machine).

In brief: the **client** controls `llama-server` instances on the **server** over
SSH, and the **server** runs the LLM models and reads configs from a shared NFS
disk.

---

## 1. Architecture

```
┌─────────────── CLIENT (GUI) ───────────────┐
│  LLM-Control_v2  (PySide6, main_ui.py)      │
│  • model scanner                            │
│  • .mod / .conf configurator                │
│  • SSH control (llmctl)                     │
│  • GPU/memory monitoring over SSH           │
│                                             │
│  ~/.ssh/id_ed25519_llm  (SSH key)           │
│  .env  (SSH_HOST, SERVER_USER, paths)       │
└───────────────┬─────────────────────────────┘
                │  SSH (key, passwordless)
                │  sudo /usr/local/bin/llmctl <action> [8081]
                ▼
┌─────────────── SERVER (rtx, 10.0.0.2) ────────────┐
│  systemd: llama-server.service        (mode 1, 8080, autostart)
│  systemd: llama-server-8081.service   (mode 3, 8081, manual)
│  /usr/local/bin/llmctl                (manager wrapper)
│  /usr/local/bin/run-llama.sh          (mode 1 launch)
│  /usr/local/bin/run-llama-8081.sh     (mode 3 launch)
│  /usr/local/bin/llama-server          (llama.cpp binary)
│  /etc/sudoers.d/llmctl                (passwordless sudo for llmctl)
│                                             │
│  NFS: /srv/storage ≡ client /media/rtx-storage (configs)
│       /srv/models  ≡ client /media/rtx-models  (models)
└─────────────────────────────────────────────────────┘
```

### Operating modes (instances)

| Port | Service                | GPU           | Autostart | Purpose                   |
|------|------------------------|---------------|:---------:|---------------------------|
| 8080 | `llama-server`         | GPU0 + GPU1   | yes       | main (mode 1)             |
| 8081 | `llama-server-8081`    | GPU1          | no        | on demand (mode 3)        |

Instances are selected by suffix: `llmctl …` → 8080, `llmctl … 8081` → 8081.

---

## 2. Mandatory dependencies (before deployment)

These components are **not installed** by `deploy-server.sh` — they are the
foundation the system runs on.

1. **NFS mounting.**
   - On the server, the shared directories are `/srv/storage` (configs) and
     `/srv/models` (models).
   - On the client, they are mounted as `/media/rtx-storage` and
     `/media/rtx-models`.
   - Configs on the server are owned by user `yuri` (edited from the client
     without sudo); binaries and services live in root directories (sudo needed).

2. **The `llama-server` binary** (llama.cpp build) on the server, e.g.
   `/usr/local/bin/llama-server`. The deployment script checks for its presence
   and warns, but does not install it automatically. How to build it from source
   for one or two RTX cards — in
   [`llama-server-installation.md`](llama-server-installation.md).

3. **An SSH key** from the client to the server (see §4).

4. **A user** on the server (default `yuri`) with sudo capability.

> If NFS and the binary are already set up (as on the current server), you can
> jump straight to §4 — software deployment.

---

## 3. Deployment on the server

### 3.1. What the script installs

`server/deploy-server.sh` installs and configures:

- `/usr/local/bin/llmctl` — instance manager wrapper
- `/usr/local/bin/run-llama.sh` — mode 1 launch (8080, both GPUs)
- `/usr/local/bin/run-llama-8081.sh` — mode 3 launch (8081, GPU1)
- `/etc/systemd/system/llama-server.service` — mode 1, **autostart**
- `/etc/systemd/system/llama-server-8081.service` — mode 3, **no autostart**
- `/etc/sudoers.d/llmctl` — `passwordless sudo` for `llmctl`

### 3.2. Installation (once)

Copy the entire `server/` directory to the server (e.g. into `/home/yuri/`), then:

```bash
# On the server:
cd /home/yuri/server
sudo ./deploy-server.sh
```

The script:

- elevates privileges via `sudo` (password is requested **once**);
- copies files with correct permissions (`755` for scripts, `644` for services,
  `440` for sudoers);
- runs `systemctl daemon-reload`, enables `llama-server` in autostart
  (`enable --now`), and ensures `llama-server-8081` is not in autostart;
- creates `/etc/sudoers.d/llmctl` (idempotent — re-running does not duplicate the
  line);
- checks the installation and prints a report.

The script is safe to re-run (idempotent).

#### Script variables (optional)

| Variable | Default | Purpose |
|----------|---------|---------|
| `PREFIX` | `/` | Root to mount under. For a test: `PREFIX=/tmp/llmtest` |
| `SUDO_USER_NAME` | `yuri` | Username for the sudoers line |
| `LLAMA_SERVER_BIN` | `${PREFIX}usr/local/bin/llama-server` | Path to the llama-server binary |
| `DRY_RUN` | `0` | Only show commands, do not execute them |

Example — see what the script would do without changing the system:

```bash
sudo DRY_RUN=1 ./deploy-server.sh
```

### 3.3. Verify after installation

```bash
# On the server:
sudo /usr/local/bin/llmctl status          # mode 1 status
sudo /usr/local/bin/llmctl status 8081     # mode 3
sudo /usr/local/bin/llmctl mode            # print mode 1 config
systemctl is-enabled llama-server          # should be "enabled"
```

If `llama-server` is not installed, the services will not start — install the
binary first (§2), then run `sudo systemctl restart llama-server`.

---

## 4. Setting up SSH access (client → server)

The app works **only with SSH keys** (passwords are not used).

### Option A — built-in wizard (recommended)

On startup, if passwordless SSH is not set up, a dialog appears:

- **Generate key** — creates `~/.ssh/id_ed25519_llm` without a password;
- **Copy key to server** — runs `ssh-copy-id` (asks for a password once);
- **Show sudoers instructions** — prints the line for `/etc/sudoers.d/llmctl`.

### Option B — manually

```bash
# On the client — generate a key:
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_llm -N "" -C "llm-control-key"

# Copy the public key to the server:
ssh-copy-id -i ~/.ssh/id_ed25519_llm.pub yuri@rtx

# Verify passwordless connection:
ssh -i ~/.ssh/id_ed25519_llm yuri@rtx "echo OK"
```

### Setting up passwordless sudo on the server

For `llmctl` to run through `sudo` without a password, on the server:

```bash
sudo visudo
# Add at the end:
yuri ALL=(ALL) NOPASSWD: /usr/local/bin/llmctl
```

Or in one command:

```bash
echo 'yuri ALL=(ALL) NOPASSWD: /usr/local/bin/llmctl' | sudo tee /etc/sudoers.d/llmctl
chmod 440 /etc/sudoers.d/llmctl
```

> **Security.** The line grants the right to run **only**
> `/usr/local/bin/llmctl` without a password — not full sudo. The sudoers file has
> permissions `440` and is owned by root.

---

## 5. Deployment on the client

### 5.1. Dependencies

```bash
pip install PySide6 python-dotenv psutil paramiko
```

### 5.2. The `.env` file

Create a `.env` in the project root:

```ini
# Paths
LAST_SCAN_PATH='/media/rtx-models'
LAST_MODS_PATH='/home/yuri/MODS'

# SSH connection to the server
SSH_HOST="rtx"
SERVER_HOST="10.0.0.2"
SERVER_USER="yuri"
SERVER_MAC="44:8A:5B:5E:79:88"

# Config paths on the server (NFS, visible to the client)
DEFAULT_CONFIG_PATH="/media/rtx-storage/llama-mode.conf"
SECOND_CONFIG_PATH="/media/rtx-storage/llama-mode-8081.conf"

# Optional
GPU_RAM_GB="12"
```

Key parameters:

| Parameter | Description |
|-----------|-------------|
| `SSH_HOST` | Server hostname (must resolve from `.ssh/config` or `/etc/hosts`) |
| `SERVER_HOST` | IP for monitoring and Wake-on-LAN |
| `SERVER_USER` | Username on the server |
| `SERVER_MAC` | Server interface MAC for WoL |
| `DEFAULT_CONFIG_PATH` | Path to the 8080 instance `.conf` |
| `SECOND_CONFIG_PATH` | Path to the 8081 instance `.conf` |

> **Important.** `.env` contains credentials (SSH paths). Do not commit it to
> Git — it is already excluded from archives and builds.

### 5.3. Running

```bash
# From source:
python main.py

# Built binary (PyInstaller):
cd dist
./LLM-Control_v2
```

### 5.4. Building the binary

```bash
pyinstaller --onefile --noconsole --name LLM-Control_v2 main.py
```

The built file is in `dist/LLM-Control_v2`; a `.env` should sit next to it (a
frozen build reads the `.env` beside the executable).

---

## 6. Instance management (`llmctl` reference)

On the server:

```bash
sudo /usr/local/bin/llmctl start        # start instance 8080
sudo /usr/local/bin/llmctl start 8081   # instance 8081
sudo /usr/local/bin/llmctl stop         # stop (force-releases the port)
sudo /usr/local/bin/llmctl restart      # restart
sudo /usr/local/bin/llmctl status       # systemd service status
sudo /usr/local/bin/llmctl mode         # print current config
sudo /usr/local/bin/llmctl logs         # journald logs (tail -f)
```

The client calls the same thing over SSH:

```bash
ssh yuri@rtx "sudo /usr/local/bin/llmctl status"
```

---

## 7. Common problems

| Symptom | Cause / solution |
|---------|------------------|
| `Permission denied (publickey)` | Key not copied; repeat `ssh-copy-id` |
| `llmctl: Command not found` / sudo password prompt | `/etc/sudoers.d/llmctl` not set up |
| `Unit llama-server.service not found` | `deploy-server.sh` did not run or `daemon-reload` was not done |
| Instance does not start after reboot | Check `systemctl is-enabled llama-server` (should be `enabled`) |
| `llama-server: No such file` | Binary not installed at `/usr/local/bin/llama-server` |
| Config not applied | The NFS config must be quoted: `EXTRA="--flash-attn"` (see `USAGE.md`) |
| WoL does not power on the server | Check the MAC in `.env` and whether WoL is enabled in BIOS |

---

## 8. What is not part of deployment

- **NFS mounting** — configured separately (depends on infrastructure).
- **Installing `llama-server`** — the llama.cpp binary is installed separately. How
  to build it from source for one or two RTX cards —
  in [`llama-server-installation.md`](llama-server-installation.md).
- **Model placement** — `.gguf` files are placed in `/srv/models/…`.

See also: [`USAGE.md`](USAGE.md) — user guide,
[`MODES.md`](MODES.md) — architecture and modes specification,
[`llama-server-installation.md`](llama-server-installation.md) — building the binary.
