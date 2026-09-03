# LLM server operating modes (rtx — 2× RTX 3060, 12 GB each)

Detailed instructions for running three modes and how they are implemented on the
server.

---

## 1. Hardware and the key constraint

The `rtx` server (10.0.0.2) has two **NVIDIA GeForce RTX 3060** cards, 12 GB each
(24 GB VRAM total).

| Mode | Model | Cards | Port | Status |
|------|-------|-------|------|--------|
| **1** | Tiel-Coder-35B-A3B-MTP-UD (Q4_K_S, ~20 GB) | both (GPU0 + GPU1) | 8080 | main, autostart |
| **2** | small model (e.g. Ornith-1.5-9B Q6_K, ~7 GB) | GPU0 | 8080 | from preset `8080/`, manual, conflicts with mode 1 |
| **3** | Ornith-1.5-9B (Q6_K, ~7 GB) | GPU1 | 8081 | manual |

**Key VRAM constraint:** the large model (~20 GB) physically spans **both** cards,
so **mode 1 is incompatible with either mode 2 or mode 3** — they cannot run
together.

Modes 2 and 3 use **different** cards (GPU0 / GPU1) and **different** ports
(8080 / 8081), so **they can run together** — two small models at once.

> If mode 1 already occupies both cards, a new model cannot see GPU1:
> `--list-devices` shows only `CUDA0` with `0 MiB free` and it fails with
> `CUDA out of memory` at `-dev 1`. This is **not a config bug**, it is lack of
> memory — stop mode 1.

---

## 2. Where things live

Client ↔ server over SSH (key `~/.ssh/id_ed25519_llm`, user `yuri`).

On the server (`/`):

| What | Path |
|------|------|
| Models | `/srv/models/` |
| Configs | `/srv/storage/` (NFS; on the client — `/media/rtx-storage/`, the **same file**) |
| Launch scripts | `/usr/local/bin/run-llama.sh`, `/usr/local/bin/run-llama-8081.sh` |
| llama-server binary | `/usr/local/bin/llama-server` |
| systemd services | `llama-server.service`, `llama-server-8081.service` |
| Manager wrapper | `/usr/local/bin/llmctl` |

**NFS nuance:** `/media/rtx-storage/` on the client is the mounted
`/srv/storage/` on the server. Edit the file in one place — the change is
immediately visible in the other. Configs are owned by user `yuri` (no sudo
needed); scripts and services live in root directories (sudo needed).

### 2.1. Preset library (`/home/yuri/MODS/`)

Presets are `.mod` files on the client. The GUI ("RTX Server") reads them from the
`LAST_MODS_PATH` directory (default `/home/yuri/MODS/`) **recursively** — including
subdirectories — shows them in the table, and on the **Apply** button writes the
contents (minus `INFO:` lines) to the selected instance's server config via NFS.

A `.mod` file matches the `.conf` format (`MODEL / HOST / PORT / THREADS / CTX /
BATCH / NGL / EXTRA` + optional `INFO:`), but `MODEL` already contains the server
path (`/srv/models/...`).

The directory is split into subdirectories by purpose:

| Subdirectory | Contains | Mode |
|--------------|----------|------|
| `large/` | current large models (both GPUs, >11 GB) | mode 1 |
| `8080/`  | current small models (GPU0, ≤11 GB) | mode 2 |
| `8081/`  | current small models (GPU1, ≤11 GB) | mode 3 |
| `old/`   | dead / archived presets | not used |
| `litera/`| exemplary (literary) presets | do not touch |

> `old/` and `litera/` are also scanned by the GUI (recursion), but not used:
> `old/` — outdated models, `litera/` — reference configs for example.

**"Preset → mode" mapping.** The radio button selects only the **port and config
file**; the actual model is determined by the chosen preset:

| Radio in GUI | Port / config file | Which preset to apply |
|--------------|--------------------|------------------------|
| **Model 1 (8080)** | `/media/rtx-storage/llama-mode.conf` | `large/` → mode 1, or `8080/` → mode 2 |
| **Model 2 (8081)** | `/media/rtx-storage/llama-mode-8081.conf` | `8081/` → mode 3 |

> Radio "Model 1" (8080) is shared between modes 1 and 2: they share port 8080 and
> GPU0, so they cannot run together — stop mode 1 first, then apply a preset from
> `8080/`.

---

## 3. Implementation on the server (how it works)

### 3.1. Config file (`.conf`)
One section of variables. Mandatory keys: `MODEL`, `HOST`, `PORT`, `THREADS`,
`CTX`, `BATCH`, `NGL`, `EXTRA`.

- `NGL=999` — "load into the GPU whatever fits".
- `EXTRA` — a multi-line string of extra keys. **Important:** a space before `\`
  on a continuation line is **mandatory**, otherwise arguments "glue" into one.
- `-dev N` — which GPUs to use (comma list: `-dev 0,1`).
- `--tensor-split f1,f2` — the fraction of the model on each GPU (for a single
  card, write `1`).

**Mode 1 — `/srv/storage/llama-mode.conf`:**
```bash
MODEL="/srv/models/Tiel-Coder-35B-A3B-MTP-UD-Q4_K_S/Tiel-Coder-35B-A3B-MTP-UD-Q4_K_S.gguf"
HOST="0.0.0.0"
PORT="8080"
THREADS="6"
CTX="98304"
BATCH="2048"
NGL="999"
EXTRA="--parallel 1 \
--tensor-split 66,62 \
--spec-type draft-mtp \
--spec-draft-n-max 2 \
--temp 0.55 \
--top-p 0.95 --top-k 20 --min-p 0.0 \
--repeat-penalty 1.0 \
-ctk q8_0 -ctv q8_0 \
--kv-unified \
-fa on \
-ub 1536 \
--load-mode mmap \
--mlock \
--ctx-checkpoints 16 \
--jinja"
```

**Mode 3 — `/srv/storage/llama-mode-8081.conf`:**
```bash
MODEL="/srv/models/Ornith-1.5-9B-Q6_K/Ornith-1.5-9B-Q6_K.gguf"
HOST="0.0.0.0"
PORT="8081"
THREADS="4"
CTX="32768"
BATCH="1024"
NGL="999"
EXTRA="--parallel 2 \
--tensor-split 1 \
--temp 0.2 \
--top-p 0.95 \
--top-k 20 \
--min-p 0.02 \
--presence-penalty 0.0 \
--repeat-penalty 1.0 \
--frequency-penalty 0.0 \
-ctk q4_0 -ctv q4_0 \
--kv-unified \
-fa on \
--jinja \
-ub 512 \
--reasoning off \
-dev 1"
```

### 3.2. Launch script (`run-llama*.sh`)
Imports the config (`source "$CONFIG"`) and launches the binary via `exec`:
```bash
exec /usr/local/bin/llama-server \
    -m "$MODEL" -t "$THREADS" -c "$CTX" -b "$BATCH" -ngl "$NGL" \
    --host "$HOST" --port "$PORT" $EXTRA
```
(In `run-llama-8081.sh` the binary path was wrong — `/usr/bin/llama-server`,
which does not exist; fixed to `/usr/local/bin/llama-server`.)

### 3.3. systemd services
- `llama-server.service` → `ExecStart=/usr/local/bin/run-llama.sh` (**mode 1**).
  `enabled` — autostart, `RequiresMountsFor=/srv/models`.
- `llama-server-8081.service` → `ExecStart=/usr/local/bin/run-llama-8081.sh`
  (**mode 3**). `Restart=no`.

### 3.4. Wrapper `llmctl`
`/usr/local/bin/llmctl <start|stop|restart|status|mode|logs> [8081]`

- Mapping: no argument → port `8080` / service `llama-server`; with `8081` →
  `llama-server-8081`.
- `start`/`stop`/`restart`/`status`/`logs` — via `sudo systemctl`
  (+ `fuser -k <port>/tcp` to force-release the port on stop).
- `mode` — prints the current config.
- **Requires passwordless sudo** on the server (see §5).

### 3.5. GUI app ("RTX Server" tab)
Two instance radio buttons:

| Radio in GUI | Corresponds to | Config | Preset | Command |
|--------------|----------------|--------|--------|---------|
| **Model 1 (port 8080, autostart)** | Mode 1 **or** 2 | `/media/rtx-storage/llama-mode.conf` | `large/` (mode 1) / `8080/` (mode 2) | `llmctl …` (no suffix) |
| **Model 2 (port 8081, manual, GPU1)** | Mode 3 | `/media/rtx-storage/llama-mode-8081.conf` | `8081/` | `llmctl 8081 …` |

Buttons: **Apply** (saves the pasted config to the file on the server via NFS),
**Start / Stop / Restart / Status / Config / Logs**.

The command goes out like this:
```
ssh -i <key> rtx "sudo /usr/local/bin/llmctl <action> <suffix>"
```
So the GUI simultaneously requires **(1)** passwordless SSH by key and
**(2)** passwordless sudo on the server.

The app's config validator catches typical ways to break a launch:
- `NGL="auto"` + manual `--tensor-split` (causes OOM);
- missing space before `\` in a multi-line `EXTRA`;
- missing mandatory keys (`MODEL`, `PORT`, `CTX`, `NGL`);
- invalid `PORT` / `CTX` / `NGL` ranges.

---

## 4. How to start each mode

### Mode 1 — large model, both cards, 8080 (main)
**From GUI:** "RTX Server" tab → radio "Model 1 (port 8080)" → **Start**.
**From terminal (llmctl):**
```bash
ssh rtx "sudo /usr/local/bin/llmctl start"
```
**systemd (autostart):**
```bash
sudo systemctl start llama-server
```

### Mode 3 — small model, GPU1, 8081
**From GUI:** "RTX Server" tab → radio "Model 2 (port 8081, GPU1)" → **Start**.
**From terminal:**
```bash
ssh rtx "sudo /usr/local/bin/llmctl start 8081"
# or
sudo systemctl start llama-server-8081
```
**Verify:** `nvidia-smi` — GPU1 is loaded; `curl http://rtx:8081/health`; in the
GUI indicator `8081: ACTIVE | … GB`.

### Mode 2 — small model, GPU0, 8080 (manual)

Presets for mode 2 live in `8080/` of the `/home/yuri/MODS/` library. Mode 2 has
no separate systemd service and shares port 8080 and GPU0 with mode 1, so it runs
**only when mode 1 is stopped**.

**A. From a preset via GUI** (recommended):
1. "Config" tab → choose a preset from `8080/` (the `.mod` table, recursive scan).
2. "Manage" tab → radio **"Model 1 (port 8080)"**.
3. **Apply** (writes the `.mod` to `/media/rtx-storage/llama-mode.conf`), then
   **Start**.
> A preset from `8080/` already contains the correct flags for a single GPU
> (`-sm none`, no `--tensor-split`, no bare `export CUDA_VISIBLE_DEVICES`);
> `-dev` is not needed — GPU0 is taken by default.

**B. One-off manual launch** (model on GPU0 via `CUDA_VISIBLE_DEVICES`, port 8080):
```bash
ssh rtx
CUDA_VISIBLE_DEVICES=0 /usr/local/bin/llama-server \
    -m /srv/models/Ornith-1.5-9B-Q6_K/Ornith-1.5-9B-Q6_K.gguf \
    -t 4 -c 32768 -b 1024 -ngl 999 \
    --host 0.0.0.0 --port 8080 \
    --parallel 2 --temp 0.2 --top-p 0.95 --top-k 20 --min-p 0.02 \
    -ctk q4_0 -ctv q4_0 --kv-unified -fa on --jinja -ub 512 --reasoning off
```
> `CUDA_VISIBLE_DEVICES=0` hides GPU0 from view, so `-dev` / `--tensor-split` are
> not needed — llama-server takes the visible GPU0 itself.

⚠️ Port 8080 is already taken by mode 1, and GPU0 is too. Mode 2 can be started
**only when mode 1 is stopped**. It is compatible only with mode 3 (different
cards and ports).

> There is no separate service for mode 2: `llmctl start` (no suffix) launches the
> same `llama-server.service` as mode 1, but with the contents of
> `llama-mode.conf` — i.e. your preset from `8080/`.

---

## 5. Requirements and dependencies

- **SSH by key** `~/.ssh/id_ed25519_llm` (passwordless) — set up with the wizard
  in the GUI ("SSH Setup").
- **Passwordless sudo** on the server for user `yuri` (file
  `/etc/sudoers.d/…`, line `NOPASSWD`). Without it, the GUI buttons and `llmctl`
  will not start the service: `sudo` will ask for a password, which a non-interactive
  SSH has none. If passwordless is not set up yet — start services manually via
  `ssh rtx` with a password prompt, or set up sudoers.
- **NFS** `/media/rtx-storage` on the client ≡ `/srv/storage` on the server —
  editing the config in any place is immediately visible in the other.

---

## 6. Troubleshooting

| Symptom | Cause | What to do |
|---------|-------|------------|
| `CUDA out of memory` / `invalid device: 1` | Both cards busy (mode 1 running) | Stop mode 1, then start modes 2/3 |
| `/usr/bin/llama-server: no such file` (code 127) | Wrong binary path | Use `/usr/local/bin/llama-server` |
| Port busy / service won't start | Another mode already on the same port | 8080: mode 1/2; 8081: mode 3. Stop the conflicting one |
| GUI buttons don't work | No passwordless sudo on server | Set up `/etc/sudoers.d/…` (see §5) or run manually |
| `Pseudo-terminal warning` | Informational SSH message | Ignored (GUI filters it) |
| Launch logs | — | GUI: "Logs" button; or `ssh rtx "sudo journalctl -u llama-server-8081 -f"` |

---

## 7. Compatibility cheat sheet

| | Mode 1 (8080, GPU0+1) | Mode 2 (8080, GPU0) | Mode 3 (8081, GPU1) |
|---|---|---|---|
| **Mode 1** | — | conflict (port + cards) | conflict (cards) |
| **Mode 2** | conflict | — | ✅ compatible |
| **Mode 3** | conflict | ✅ compatible | — |

**Working combinations:**
- **Mode 1 alone** — large model on both cards.
- **Mode 2 + Mode 3** — two small models at once (GPU0/8080 + GPU1/8081).
