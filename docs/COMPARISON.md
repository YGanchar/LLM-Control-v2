# LLM-Control v2 — a control panel for your local AI server

> English version: this file. Русская версия: [COMPARISON_RU.md](COMPARISON_RU.md)

## In short

**LLM-Control v2** is a free (GPL-3.0) GUI control panel for `llama-server` running on your own GPU machine. Start and stop models, a library of launch presets, live VRAM/CPU/GPU monitoring, Wake-on-LAN — all from a window on your workstation while the server hums in the closet. Inference is done by **stock llama-server** from llama.cpp: no forks, no shim layers, no vendor lock-in.

## The problem it solves

Local LLMs usually live on a dedicated GPU box: a silent workstation for you, the server in a closet. Then the routine begins: ssh → `systemctl edit` → tweak flags → restart → `watch nvidia-smi` → out of VRAM → tweak again… Every chat interface offers you a "Generate" button, but **nobody offers a panel for operating the server**. LLM-Control is exactly that.

## Philosophy: a thin client

The panel never touches the model itself — and that is its strength:

- **You are not tied to an engine version.** Upgrade llama-server and the panel keeps working. New flags (KV cache quantization `-ctk/-ctv`, speculative decoding with an MTP draft, `--jinja`, `--tensor-split`) simply go into the config.
- **No ML stack on the client.** A small PySide6 app: no CUDA dependencies on the workstation.
- **Everything is transparent.** Configs are plain text files, control is plain systemd. The panel is a convenience layer, not a black box.

## Feature highlights

- **Two llama-server instances** (ports 8080/8081): one across both GPUs via `--tensor-split`, the other pinned to the second GPU; switching is one radio button.
- **Launch presets (.mod)**: a config library per model, NGL/CTX/BATCH auto-pick by quant and size, one-click deployment to the server.
- **Model scanner**: recursive walk over `.gguf` directories with sizes and vision-model tags.
- **Config validator**: catches real-world blunders before a restart — glued arguments in a multi-line `EXTRA`, the `NGL=auto` + `--tensor-split` combination (a known OOM), typos in required keys.
- **Live monitoring**: server CPU/RAM, per-card VRAM and power draw, VRAM **per instance** — every 2 seconds in the status bar.
- **Power**: one-click Wake-on-LAN, graceful server shutdown, monitor self-quieting after poweroff.
- **Logs**: a `journalctl -f` stream right in the window, with critical errors (OOM, CUDA) highlighted.
- **First-run SSH setup** from a dialog: key generation, copying to the server, sudoers instructions.
- **UI languages**: English, Russian, Spanish.

## How it compares

| | **LLM-Control v2** | LM Studio | Ollama | Open WebUI | text-gen-webui | KoboldCpp |
|---|---|---|---|---|---|---|
| Controls a **remote headless server** over SSH | ✅ | — | — | — | — | — |
| Full llama.cpp flag surface (KV quantization, speculative decoding, tensor-split) | ✅ | partial¹ | hidden² | n/a | partial | partial |
| systemd services: start/stop/restart/logs from the GUI | ✅ | — | — | — | — | — |
| Multiple instances on multi-GPU | ✅ | — | — | — | — | — |
| Per-model launch preset library | ✅ | partial³ | Modelfile | — | — | — |
| Local .gguf library scanner | ✅ | ✅ | internal registry | — | ✅ | ✅ |
| VRAM/GPU/power monitoring per card and per process | ✅ | partial | — | — | — | — |
| Wake-on-LAN and server poweroff | ✅ | — | — | — | — | — |
| Config sanity checks before launch | ✅ | — | — | — | — | — |
| Model downloads from hubs | — | ✅ | ✅ | ✅ | ✅ | — |
| Chat interface | —⁴ | ✅ | — | ✅ | ✅ | ✅ |
| License | **GPL-3.0** | proprietary | MIT | Open WebUI license | AGPL-3.0 | MIT |
| Client | lightweight GUI, no ML stack | desktop app | service + CLI | web | server-side monolith | single binary on the server |

¹ Has a settings UI, but it runs where it is installed and drives the local runtime.
² Ollama deliberately hides llama.cpp parameters; only a few environment variables are exposed.
³ Load settings can be saved, but there is no separate preset library or validation.
⁴ LLM-Control is an operations panel, not a chat. It pairs perfectly with any chat client speaking the OpenAI-compatible API — exactly the endpoint llama-server exposes.

## An honest "choose like this"

- **Want install-download-chat on your desktop** → LM Studio or GPT4All. That is their home turf.
- **Need an API service with a model registry and zero manual tuning** → Ollama. An excellent tool with a different mission.
- **Need a nice web chat for a team** → Open WebUI. It works great **alongside** a llama-server managed by LLM-Control: chat in WebUI, operations in LLM-Control.
- **You own a GPU box and want stock llama.cpp with every flag, presets, monitoring, and power control at a button's reach** → that is exactly the niche of LLM-Control v2.

## Who it is NOT for

To be fair: if you have a single desktop and just want to chat with a model, you don't need a panel — grab LM Studio. If you want a model-download manager — grab Ollama. LLM-Control does not replace them; it covers what they don't think about: **operating your own inference server**.

## Bottom line

LLM-Control v2 is the GUI panel for llama-server you would inevitably build for yourself over a weekend: ssh commands, presets, monitoring, WoL. Except it is already written, battle-tested (the validator codifies real OOM lessons), and open under GPL-3.0.

**Repository:** [github.com/YGanchar/LLM-Control-v2](https://github.com/YGanchar/LLM-Control-v2)
