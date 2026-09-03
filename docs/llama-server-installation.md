# Installing llama-server from source (RTX, 1 and 2 cards)

This guide builds `llama-server` (part of llama.cpp) with CUDA support and
installs it to `/usr/local/bin/llama-server` — the path the LLM-Control system
expects (`run-llama.sh`, `run-llama-8081.sh`, `llmctl`).

One build works for all cases: **a single binary** runs on one card or two. The
difference between "one" and "two" cards has two parts:

1. **Compilation** — which GPU architectures to bake into the binary (see below).
2. **Runtime** — how to split the model across cards at launch
   (`--tensor-split`, `-ngl`, `--parallel`) — briefly in §6.

> Server: i5-4570, RTX 3060 12 GB (Ampere architecture, sm_86).
> Target quantizations: Q5_K_M / Q6_K_L, ~35–40 tok/s.

---

## 1. What to know about GPU architecture

llama.cpp compiles CUDA code for a specific compute capability ("sm"). If you
bake in only your own card, the binary runs faster and is smaller. If the cards
differ, you must bake in both architectures.

| NVIDIA series | Examples | compute capability |
|---------------|----------|:------------------:|
| Maxwell | GTX 980 | sm_5x (52) |
| Pascal | GTX 1060, 1080 | sm_61 |
| Turing | GTX 16xx, RTX 2060 | sm_75 |
| **Ampere** | **RTX 3060, 3080** | **sm_86** |
| Ada Lovelace | RTX 4060, 4090 | sm_89 |
| Hopper | H100 | sm_90 |

For this server — **sm_86 (RTX 3060)**. If the second card is, say, an RTX 4070,
that is sm_89, and the binary must be built for both at once (`86;89`).

Check your own card like this:

```bash
nvidia-smi                       # card model
# Full list of architectures: https://developer.nvidia.com/cuda-gpus
```

---

## 2. Dependencies (installed on the server)

```bash
sudo apt update
sudo apt install -y build-essential cmake git pkg-config nvidia-driver
```

- `build-essential`, `cmake`, `git`, `pkg-config` — build tools.
- `nvidia-driver` — the driver; after installing, reboot the server and check
  `nvidia-smi` (it should see the card without errors).

### CUDA toolkit (for nvcc)

CUDA compilation needs the `nvcc` compiler. Two paths:

**A. From packages (simpler, but older version):**

```bash
sudo apt install -y cuda-toolkit          # or cuda-toolkit-12-6, cuda-toolkit-12-2 …
```

**B. Fresh toolkit from NVIDIA (runfile):** download
`cuda_<ver>_linux.run` from https://developer.nvidia.com/cuda-downloads and
install only the compiler:

```bash
sudo sh cuda_12.6.0_550.54.14_linux.run --toolkit   # without the driver!
export PATH=/usr/local/cuda/bin:$PATH
```

Verify:

```bash
nvcc --version        # should print the Toolkit version
```

> Tip: if you don't want to pull in the whole toolkit with cuBLAS, build llama.cpp
> in the lightweight mode without cuBLAS — see §4, "Lightweight build". There `nvcc`
> is not needed for cuBLAS, but the CUDA compiler itself is still required.

---

## 3. Download the sources

```bash
cd /usr/local/src
git clone https://github.com/llamacpp/llama.cpp
cd llama.cpp
```

> The repository is officially moving to the `ggml-org` organization; if
> `llamacpp/llama.cpp` stops working, use
> `https://github.com/ggml-org/llama.cpp`.

Optionally, a specific stable version:

```bash
git checkout llama-v1.6.2        # replace with the current tag from https://github.com/llamacpp/llama.cpp/tags
```

---

## 4. Building

### 4.1. One card (RTX 3060, sm_86)

Bake the binary only for your own architecture — faster build, smaller size,
maximum speed:

```bash
cmake -B build \
    -DGGML_CUDA=ON \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CUDA_ARCHITECTURES=86

cmake --build build --config Release -j$(nproc)
```

- `-DGGML_CUDA=ON` — enable the CUDA backend.
- `-DCMAKE_BUILD_TYPE=Release` — optimization.
- `-DCMAKE_CUDA_ARCHITECTURES=86` — target architecture (sm_86 = RTX 30xx).

Result: `build/bin/llama-server`.

### 4.2. Two cards

**Case A — cards are identical** (e.g. two RTX 3060). The architecture is one
(`sm_86`), so **the compilation is identical to §4.1** —
`-DCMAKE_CUDA_ARCHITECTURES=86`. The split between cards is configured only at
start (§6).

**Case B — cards differ** (e.g. RTX 3060 sm_86 + RTX 4070 sm_89). Bake both
architectures via a semicolon:

```bash
cmake -B build \
    -DGGML_CUDA=ON \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CUDA_ARCHITECTURES=86;89

cmake --build build --config Release -j$(nproc)
```

The resulting binary runs on any of these cards (and their combination).

> Exact architecture numbers are in the §1 table. For one card, give one number;
> for several, use `;` (e.g. `75;86` for Turing+Ampere).

### 4.3. Lightweight build (without cuBLAS)

If you don't want to install the CUDA toolkit with cuBLAS, or a normal build fails
with "cuBLAS not found", build a clean CUDA matmul:

```bash
cmake -B build \
    -DGGML_CUDA=ON \
    -DGGML_CUDA_FORCE_MMQ=ON \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CUDA_ARCHITECTURES=86

cmake --build build --config Release -j$(nproc)
```

- `-DGGML_CUDA_FORCE_MMQ=ON` — use the built-in quantized matmul instead of cuBLAS.
  Smaller binary, more reliable build, nearly the same speed for quantized models
  (Q4/Q5/Q6). Good for a home server.

> For two different cards, combine:
> `-DGGML_CUDA_FORCE_MMQ=ON` + `-DCMAKE_CUDA_ARCHITECTURES=86;89`.

---

## 5. Installing the binary

After a successful build, copy the binary to the system directory:

```bash
install -m 0755 build/bin/llama-server /usr/local/bin/llama-server
/usr/local/bin/llama-server --help | head -n 5     # verify: prints help
```

Verify card visibility (without launching a model):

```bash
nvidia-smi
```

> The binary is already at `/usr/local/bin/llama-server` — that is where
> `run-llama.sh`, `run-llama-8081.sh` and `llmctl` expect it. If the path is
> different, adjust them or create a symbolic link.

---

## 6. Running on one and on two cards

The build does not depend on the number of cards — the number is chosen by launch
flags. A specific quantization model (Q5_K_M / Q6_K_L) runs the same either way.

### 6.1. One card

The whole model on one GPU. A large enough `-ngl` (layers per GPU) suffices:

```bash
/usr/local/bin/llama-server \
    -m /srv/models/model.Q5_K_M.gguf \
    -ngl 999 \
    --host 0.0.0.0 --port 8080 \
    -t 8 -c 8192 -b 512
```

- `-ngl 999` — put as many layers as fit in VRAM (llama.cpp counts how much fits
  itself; the rest goes to CPU).
- `-t` CPU threads, `-c` context size, `-b` batch size — by memory.

### 6.2. Two cards (model split between GPU0 and GPU1)

Split weights across cards with `--tensor-split`. These are **fractions (numbers
from 0 to 1, sum ≤ 1.0)**, not percentages: the fraction shows what portion of the
model each card "weighs". For two 12 GB cards of the same size, split evenly:

```bash
/usr/local/bin/llama-server \
    -m /srv/models/model.Q6_K_L.gguf \
    -ngl 999 \
    --tensor-split 0.5,0.5 \
    --parallel 2 \
    --host 0.0.0.0 --port 8080 \
    -t 8 -c 8192 -b 512
```

- `--tensor-split 0.5,0.5` — split the model between GPU0 and GPU1 evenly.
- If the cards have **different** memory (e.g. 12 GB + 24 GB), split in
  proportion to capacity: `--tensor-split 0.33,0.67`.
- `--parallel 2` — two request-processing pipelines (one per card); raises
  throughput for batch processing. Omit it if you don't need maximum throughput.

The project already uses this approach: the main instance (`llama-server`, port
8080) runs on **GPU0+GPU1**, and the separate one (`llama-server-8081`, port 8081)
on **GPU1**.

### 6.3. Running on one specific card (e.g. only GPU1)

To make GPU1 "zero" and put the whole model on it:

```bash
CUDA_VISIBLE_DEVICES=1 /usr/local/bin/llama-server \
    -m /srv/models/model.Q5_K_M.gguf \
    -ngl 999 \
    --host 0.0.0.0 --port 8081 \
    -t 8 -c 8192 -b 512
```

`CUDA_VISIBLE_DEVICES=1` hides GPU0, so GPU1 is used as the only one.

---

## 7. Possible problems

| Sign | Cause and solution |
|------|--------------------|
| `nvcc: command not found` | CUDA toolkit not installed (§2). Install it or add `/usr/local/cuda/bin` to `PATH`. |
| `cuBLAS not found` during build | Use the MMQ mode: add `-DGGML_CUDA_FORCE_MMQ=ON` (§4.3). |
| `Unsupported gpu architecture 'sm_XXXX'` during build | Wrong architecture number. Set the right one from §1 (e.g. `86` for RTX 3060). |
| Build fails on `-j$(nproc)` due to memory | Build with fewer threads: `-j4`. |
| `llama-server: error while loading shared libraries: libcuda.so` | Driver not installed / wrong. `sudo apt install nvidia-driver`, reboot. |
| "out of memory" error when launching a model | Reduce `-ngl` or change `--tensor-split` (§6). |
| Model loads slowly, lots of CPU | `-ngl` too small — increase it so more layers fit in VRAM. |

---

## 8. Quick reference

**One RTX 3060 (sm_86):**

```bash
cmake -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=86
cmake --build build --config Release -j$(nproc)
install -m 0755 build/bin/llama-server /usr/local/bin/llama-server
```

**Two different RTX (e.g. sm_86 + sm_89):**

```bash
cmake -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=86;89
cmake --build build --config Release -j$(nproc)
install -m 0755 build/bin/llama-server /usr/local/bin/llama-server
```

Running on two cards — `--tensor-split 0.5,0.5 -ngl 999 --parallel 2` (§6.2).
