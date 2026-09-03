# LLM-Control v2 — User Guide

**LLM-Control v2** is a desktop application (Python/PySide6) for managing an RTX
GPU server and running local LLMs through `llama-server`.

### Main features

1. **Model scanner** — searches for `.gguf` files on disk and shows them in a
   table with size and vision-module info.
2. **Configurator** — creates and edits `.mod` files (llama-server launch
   configuration) with automatic parameter selection.
3. **Server management** — remote control of llama-server instances over SSH,
   Wake-on-LAN, and real-time resource monitoring.

---

## Project structure

```
LLM-Control-v2/
├── .env                    # Configuration (paths, SSH params, MAC address)
├── main.py                 # Application entry point
├── main_ui.py              # Main window (widget coordination)
├── scanner_widget.py       # Model scanner widget
├── config_widget.py        # .mod config widget
├── server_widget.py        # Server management widget
├── model_layers.json       # Model size → n_layer mapping
├── services/
│   ├── model_scanner.py    # Filesystem scanning
│   ├── system_monitor.py   # Server monitoring over SSH
│   ├── server_control.py   # Local process control (stub)
│   ├── ssh_manager.py      # Shared SSH access: key finding + arg building
│   ├── mod_generator.py    # .mod generator (reference)
│   └── ssh_setup.py        # SSH access setup wizard
├── server/                 # Files for server deployment (llmctl, systemd, deploy script)
├── docs/DEPLOYMENT.md      # Full deployment guide (server + client)
└── dist/                   # Built executable (PyInstaller)
```

---

## Requirements

### System requirements
- **OS:** Linux (Ubuntu 20.04+)
- **Python:** 3.8+ (for development)
- **GPU:** NVIDIA RTX (with drivers and CUDA)
- **Network:** SSH connection to the RTX server

### Dependencies

```bash
pip install PySide6 python-dotenv psutil paramiko
```

### Server setup (remote RTX server)

> **Full step-by-step deployment guide (server + client) is in**
> [`docs/DEPLOYMENT.md`](DEPLOYMENT.md). Here is a brief orientation.

### Mandatory requirements

1. Install `llama-server` and `llmctl` on the server (automated by
   `server/deploy-server.sh`)
2. Set up SSH keys for passwordless access
3. Enable Wake-on-LAN on the server's network card
4. Set up NFS mounts for shared directories (`/srv/storage`, `/srv/models` on
   the server; `/media/rtx-storage`, `/media/rtx-models` on the client)

### SSH key setup (mandatory)

The app uses **SSH keys only** for authentication. Passwords are no longer
supported.

**Step 1: Generate an SSH key (if you don't have one)**

```bash
# On the client (local machine):
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_llm -N "" -C "llm-control-key"
```

**Step 2: Copy the public key to the server**

```bash
# Copy the public key to the server:
ssh-copy-id -i ~/.ssh/id_ed25519_llm.pub yuri@rtx

# Or manually:
cat ~/.ssh/id_ed25519_llm.pub | ssh yuri@rtx "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"

# Verify:
ssh -i ~/.ssh/id_ed25519_llm yuri@rtx "echo OK"
```

**Step 3: Set up sudoers on the server (for passwordless sudo)**

```bash
# On the RTX server:
sudo visudo

# Add a line (replace 'yuri' with your username):
yuri ALL=(ALL) NOPASSWD: /usr/local/bin/llmctl
```

Or in one command:

```bash
# On the server:
echo 'yuri ALL=(ALL) NOPASSWD: /usr/local/bin/llmctl' | sudo tee -a /etc/sudoers.d/llmctl
```

### Built-in SSH setup wizard

The app has a built-in SSH setup wizard. If keys are not found or the connection
fails, a dialog appears on startup with suggestions:

- **Generate key** — creates a new passwordless SSH key
- **Copy key to server** — runs `ssh-copy-id`
- **Show sudoers instructions** — prints the line for `/etc/sudoers.d/llmctl`

---

## Configuration (.env)

Create a `.env` file in the project root:

```ini
# Paths
LAST_SCAN_PATH='/media/rtx-models'
LAST_MODS_PATH='/home/yuri/MODS/new'

# SSH connection to the server
SSH_HOST="rtx-auto"
SERVER_HOST="10.0.0.2"
SERVER_USER="yuri"
SERVER_MAC="44:8A:5B:5E:79:88"

# Config paths on the server
DEFAULT_CONFIG_PATH="/media/rtx-storage/llama-mode.conf"
SECOND_CONFIG_PATH="/media/rtx-storage/llama-mode-8081.conf"

# Optional
GPU_RAM_GB="12"
```

### Important parameters

| Parameter | Description |
|-----------|-------------|
| `SSH_HOST` | Server hostname or IP (must resolve from `.ssh/config` or `/etc/hosts`) |
| `SERVER_HOST` | Server IP for monitoring and WoL |
| `SERVER_USER` | Username on the server |
| `SERVER_MAC` | Server network interface MAC for Wake-on-LAN |
| `DEFAULT_CONFIG_PATH` | Path to the `.conf` file for the 8080 instance |
| `SECOND_CONFIG_PATH` | Path to the `.conf` file for the 8081 instance |

> **Note:** `SERVER_PASS` is no longer used. Authentication is via SSH keys only.

---

## Running the app

### From source

```bash
cd /home/yuri/projects/LLM-Cluster/LLM-Control-v2
python main.py
```

### Built executable

```bash
cd dist
./LLM-Control_v2
```

### Build (PyInstaller)

```bash
pyinstaller --onefile --noconsole --name LLM-Control_v2 main.py
```

---

## Step-by-step usage

### 1. Scan models

1. Open the **"Model Scanner"** tab
2. Click **"Browse..."** and select a directory with `.gguf` files (e.g.
   `/media/rtx-models`)
3. Click **"Scan"**
4. Wait for the scan to finish
5. Find the needed model in the table (click column headers to sort)
6. **Double-click** a row to select the model and switch to the **"Model
   Parameters"** tab

### 2. Configure the model

On the **"Model Parameters"** tab:

1. **Select a directory with .mod files** (the "Browse" button in the top-right)
2. Enter or select a model name
3. Review the generated configuration in the right text area
4. Edit parameters as needed:
   - `MODEL` — path to the model on the server
   - `PORT` — port (8080 or 8081)
   - `CTX` — context size
   - `NGL` — number of layers loaded into the GPU
   - `BATCH` — batch size
   - `THREADS` — number of CPU threads
   - `EXTRA` — extra arguments
5. Click **"Save"** to write to the `.mod` file
6. Click **"Server"** to switch to server management with this configuration

#### Automatic parameter selection

The app selects parameters based on:

- Model size (GB)
- Quantization (Q8_0, Q6_K, Q4_K_M, etc.)
- GPU VRAM size (`GPU_RAM_GB` in `.env`)

### 3. Manage the server

On the **"RTX Server"** tab:

#### Switching instances

Use the radio buttons at the top to choose the managed instance:
- **Model 1 (port 8080, autostart)** — main instance
- **Model 2 (port 8081, manual, GPU1)** — additional instance

#### Main operations

| Button | Action |
|--------|--------|
| **Apply** | Save the configuration from the text area to the `.conf` file on the server |
| **Start** | Start llama-server with the current configuration |
| **Stop** | Stop the current instance |
| **Restart** | Restart the current instance |
| **Status** | Show the current instance status |
| **Config** | Show the current server configuration |
| **Logs** | Show server logs in real time |

#### Power management

| Button | Action |
|--------|--------|
| **Power on (WoL)** | Send a Magic Packet to power on the server |
| **Power off (SSH)** | Gracefully power off the server via SSH |

#### Config validation

Before saving, the app checks:

- Presence of mandatory parameters: `MODEL`, `PORT`, `CTX`, `NGL`
- Valid port range (1–65535)
- Minimum context size (≥8)
- Valid `NGL` (>0 or "auto")
- Conflict of `NGL="auto"` with manual `--tensor-split` (causes OOM)
- No glued lines in multi-line values (space before `\`)

---

## Resource monitoring

The status panel at the bottom of the main window shows:

| Indicator | Description |
|-----------|-------------|
| **SRV CPU** | Server CPU load (%) |
| **SRV RAM** | Server RAM usage (%) |
| **8080** | Instance status on port 8080 (ACTIVE/OFFLINE + VRAM) |
| **8081** | Instance status on port 8081 (ACTIVE/OFFLINE + VRAM) |
| **GPU0/1** | VRAM usage and power draw of each GPU |

Data refreshes every 2 seconds.

---

## .mod file format

A `.mod` file is a configuration for launching llama-server:

```ini
MODEL="/srv/models/NVIDIA-Nemotron-3-Nano-4B-Q8_0/NVIDIA-Nemotron-3-Nano-4B-Q8_0.gguf"
HOST="0.0.0.0"
PORT="8080"

THREADS="4"

CTX="32768"
BATCH="320"
NGL="60"

EXTRA="--flash-attn"
```

### Mandatory parameters

- `MODEL` — full path to the `.gguf` file on the server
- `PORT` — connection port (usually 8080 or 8081)
- `CTX` — context window size
- `NGL` — number of layers in the GPU (or "auto" for automatic selection)

### Optional parameters

- `HOST` — bind address (default `0.0.0.0`)
- `THREADS` — number of CPU threads (default 4)
- `BATCH` — batch size (default 320)
- `EXTRA` — extra command-line arguments

---

## Model distribution across the server

The app translates client paths into server paths:

```
Client: /media/rtx-models/NVIDIA-Nemotron-3-Nano-4B-Q8_0/model.gguf
         ↓
Server: /srv/models/NVIDIA-Nemotron-3-Nano-4B-Q8_0/model.gguf
```

Each model is placed in its own subdirectory on the server.

---

## Troubleshooting

### SSH connection fails

1. Verify that `SSH_HOST` resolves correctly
2. Make sure the SSH key is set up and works:
   ```bash
   ssh -i ~/.ssh/id_ed25519_llm yuri@rtx "echo OK"
   ```
3. Check that the server is powered on (try WoL)
4. Check the logs in the server text area

### WoL doesn't work

1. Make sure the MAC in `.env` matches the server's MAC
2. Verify that Wake-on-LAN is enabled in the server's BIOS/UEFI
3. Verify that the server's network card supports WoL
4. Make sure the router broadcasts broadcast packets

### "SSH key not found" error

The app searches for keys in this order:

1. `~/.ssh/id_ed25519_llm` (dedicated LLM-Control key)
2. `~/.ssh/id_ed25519` (standard Ed25519)
3. `~/.ssh/id_rsa` (standard RSA)

The search itself is implemented in `services/ssh_manager.py` (method
`SSHManager.get_ssh_key_path`) and is used by both the monitor and the server
widget.

If no key is found:

- Use the built-in setup wizard (appears on startup)
- Or generate a key manually:
  ```bash
  ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_llm -N "" -C "llm-control-key"
  ssh-copy-id -i ~/.ssh/id_ed25519_llm.pub yuri@rtx
  ```

### Configuration validation error

The app shows a list of problems. The most common:

- **Missing mandatory parameters** — add `MODEL`, `PORT`, `CTX`, `NGL`
- **PORT: invalid range** — use a port from 1 to 65535
- **CTX: too small** — minimum 8
- **NGL="auto" with --tensor-split** — remove `--tensor-split` or set NGL to a number

### Monitor shows "OFFLINE"

1. Check that the server is powered on
2. Check that port 22 (SSH) is open
3. Verify that `SERVER_HOST` in `.env` is correct

### App won't start

1. Make sure all dependencies are installed:
   ```bash
   pip install PySide6 python-dotenv psutil paramiko
   ```
2. Check that the `.env` file exists in the project root

---

## Logging

All actions are logged to the console and (if configured) a file. Format:

```
2026-08-10 12:34:56,789 - INFO - [MAIN] Application startup. Directory: /home/yuri/projects/LLM-Cluster/LLM-Control-v2
```

Logging levels:

- **INFO** — normal events
- **WARNING** — warnings (e.g. SSH key not found)
- **ERROR** — errors
- **CRITICAL** — critical errors after which the app terminates

---

## Security

### Authentication

The app uses **SSH keys only** for authentication. Passwords are no longer
supported.

**Recommendations:**

- Store the private key in a safe place
- Do not commit SSH keys to Git
- Use limited privileges for the user
- Configure `sudoers` for `llmctl` (removes the need for full sudo)

### SSH keys

The app searches for keys in this order:

1. `~/.ssh/id_ed25519_llm` (dedicated LLM-Control key)
2. `~/.ssh/id_ed25519` (standard Ed25519)
3. `~/.ssh/id_rsa` (standard RSA)

An Ed25519 key without a passphrase is recommended for automatic operation.

---

## Contacts and support

If you run into problems, check:

1. App logs (console)
2. `.env` correctness
3. Server connection (`ping SSH_HOST`)
4. Server status (indicators in the bottom panel)

---

## License

This project is distributed under the **GPL-3.0** license. See the
[GPL-3.0 license](../LICENSE) text.
