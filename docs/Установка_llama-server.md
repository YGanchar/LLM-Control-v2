# Установка llama-server из исходников (RTX, 1 и 2 карты)

Инструкция собирает `llama-server` (часть llama.cpp) с поддержкой CUDA и
устанавливает его в `/usr/local/bin/llama-server` — тот путь, который ожидает
комплекс LLM-Control (`run-llama.sh`, `run-llama-8081.sh`, `llmctl`).

Сборка одна на все случаи: **один бинарник** запускается и на одной карте, и на
двух. Разница между «одной» и «двумя» картами состоит из двух частей:

1. **Компиляция** — какие архитектуры GPU зашить в бинарник (см. ниже).
2. **Запуск** — как разделить модель между картами в рантайме
   (`--tensor-split`, `-ngl`, `--parallel`) — кратко в п. 6.

> Сервер: i5-4570, RTX 3060 12 ГБ (архитектура Ampere, sm_86).
> Целевые кванты: Q5_K_M / Q6_K_L, ~35–40 ток/с.

---

## 1. Что нужно знать об архитектуре видеокарт

llama.cpp компилирует CUDA-код под конкретную вычислительную архитектуру
(compute capability, «sm»). Если зашить только свою карту — бинарник будет
быстрее и меньше. Если карты разные — нужно зашить архитектуры обеих.

| Серия NVIDIA            | Примеры              | compute capability |
|-------------------------|----------------------|:------------------:|
| Maxwell                 | GTX 980              | sm_5x (52)         |
| Pascal                  | GTX 1060, 1080       | sm_61              |
| Turing                  | GTX 16xx, RTX 2060   | sm_75              |
| **Ampere**              | **RTX 3060, 3080**   | **sm_86**          |
| Ada Lovelace            | RTX 4060, 4090       | sm_89              |
| Hopper                  | H100                 | sm_90              |

Для этого сервера — **sm_86 (RTX 3060)**. Если вторая карта, например, RTX 4070,
то это sm_89, и бинарник надо собирать сразу под обе (`86;89`).

Проверить свою карту можно так:

```bash
nvidia-smi                       # модель карты
# полный список архитектур: https://developer.nvidia.com/cuda-gpus
```

---

## 2. Зависимости (устанавливаются на сервер)

```bash
sudo apt update
sudo apt install -y build-essential cmake git pkg-config nvidia-driver
```

- `build-essential`, `cmake`, `git`, `pkg-config` — инструменты сборки.
- `nvidia-driver` — драйвер; после установки перепидите сервер и проверьте
  `nvidia-smi` (должен видеть карту без ошибок).

### CUDA-тулкет (для nvcc)

Для CUDA-сборки нужен компилятор `nvcc`. Два пути:

**А. Из пакетов (проще, но версия старее):**

```bash
sudo apt install -y cuda-toolkit          # или cuda-toolkit-12-6, cuda-toolkit-12-2 …
```

**Б. Свежий тулкет с сайта NVIDIA (runfile):** скачайте `cuda_<ver>_linux.run`
с https://developer.nvidia.com/cuda-downloads и установите только компилятор:

```bash
sudo sh cuda_12.6.0_550.54.14_linux.run --toolkit   # без драйвера!
export PATH=/usr/local/cuda/bin:$PATH
```

Проверка:

```bash
nvcc --version        # должна показать версию Toolkit
```

> Совет: если не хотите тащить весь тулкет с cuBLAS, соберите llama.cpp в
> лёгком режиме без cuBLAS — см. п. 4, «Облегчённая сборка». Там `nvcc` не
> нужен для cuBLAS, но сам компилятор CUDA всё равно требуется.

---

## 3. Скачать исходники

```bash
cd /usr/local/src
git clone https://github.com/llamacpp/llama.cpp
cd llama.cpp
```

> Репозиторий официально переносится в организацию `ggml-org`; если
> `llamacpp/llama.cpp` перестанет работать, используйте
> `https://github.com/ggml-org/llama.cpp`.

По желанию — конкретная стабильная версия:

```bash
git checkout llama-v1.6.2        # замените на актуальный тег из https://github.com/llamacpp/llama.cpp/tags
```

---

## 4. Сборка

### 4.1. Одна карта (RTX 3060, sm_86)

Зашиваем бинарник только под свою архитектуру — быстрее сборка, меньше размер,
максимальная скорость:

```bash
cmake -B build \
    -DGGML_CUDA=ON \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CUDA_ARCHITECTURES=86

cmake --build build --config Release -j$(nproc)
```

- `-DGGML_CUDA=ON` — включить CUDA-бэкенд.
- `-DCMAKE_BUILD_TYPE=Release` — оптимизация.
- `-DCMAKE_CUDA_ARCHITECTURES=86` — целевая архитектура (sm_86 = RTX 30xx).

Результат: `build/bin/llama-server`.

### 4.2. Две карты

**Случай А — карты одинаковые** (например, две RTX 3060). Архитектура одна
(`sm_86`), поэтому **компиляция идентична п. 4.1** — `-DCMAKE_CUDA_ARCHITECTURES=86`.
Разделение между картами настраивается только на старте (п. 6).

**Случай Б — карты разные** (например, RTX 3060 sm_86 + RTX 4070 sm_89).
Зашиваем обе архитектуры через точку с запятой:

```bash
cmake -B build \
    -DGGML_CUDA=ON \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CUDA_ARCHITECTURES=86;89

cmake --build build --config Release -j$(nproc)
```

Полученный бинарник запустится на любой из этих карт (и на их комбинации).

> Точные номера архитектур — в таблице п. 1. Для одной карты указывайте один
> номер; для нескольких — через `;` (например `75;86` для Turing+Ampere).

### 4.3. Облегчённая сборка (без cuBLAS)

Если не хотите ставить CUDA-тулкет с cuBLAS, или обычная сборка падает с
ошибкой «cuBLAS not found», соберите чистый CUDA-матмул:

```bash
cmake -B build \
    -DGGML_CUDA=ON \
    -DGGML_CUDA_FORCE_MMQ=ON \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CUDA_ARCHITECTURES=86

cmake --build build --config Release -j$(nproc)
```

- `-DGGML_CUDA_FORCE_MMQ=ON` — использовать встроенный quantized matmul вместо
  cuBLAS. Бинарник меньше, сборка надёжнее, для квантованных моделей (Q4/Q5/Q6)
  скорость почти такая же. Хорош для домашнего сервера.

> Для двух разных карт комбинируйте: `-DGGML_CUDA_FORCE_MMQ=ON`
> + `-DCMAKE_CUDA_ARCHITECTURES=86;89`.

---

## 5. Установка бинарника

После успешной сборки скопируйте бинарник в системный каталог:

```bash
install -m 0755 build/bin/llama-server /usr/local/bin/llama-server
/usr/local/bin/llama-server --help | head -n 5     # проверка: выводит справку
```

Проверка видимости карты (без запуска модели):

```bash
nvidia-smi
```

> Бинарник уже прописан в `/usr/local/bin/llama-server` — именно туда его
> ожидают `run-llama.sh`, `run-llama-8081.sh` и `llmctl`. Если путь другой —
> скорректируйте их или создайте символическую ссылку.

---

## 6. Запуск на одной и на двух картах

Сборка не зависит числа карт — число выбирается флагами запуска. Модель
конкретного кванта (Q5_K_M / Q6_K_L) запускается одинаково.

### 6.1. Одна карта

Модель целиком на одной GPU. Достаточно большого `-ngl` (число слоёв на GPU):

```bash
/usr/local/bin/llama-server \
    -m /srv/models/модель.Q5_K_M.gguf \
    -ngl 999 \
    --host 0.0.0.0 --port 8080 \
    -t 8 -c 8192 -b 512
```

- `-ngl 999` — положить в VRAM максимально много слоёв (llama.cpp сам
  досчитает, сколько влезает, остальное — в CPU).
- `-t` потоки CPU, `-c` размер контекста, `-b` размер пачки — по памяти.

### 6.2. Две карты (модель разделена между GPU0 и GPU1)

Разделение весов по картам через `--tensor-split`. Это **доли (числа от 0 до 1,
сумма ≤ 1.0)**, а не проценты: доля показывает, какую часть модели «весит»
каждая карта. Для двух одинаковых по 12 ГБ — поровну:

```bash
/usr/local/bin/llama-server \
    -m /srv/models/модель.Q6_K_L.gguf \
    -ngl 999 \
    --tensor-split 0.5,0.5 \
    --parallel 2 \
    --host 0.0.0.0 --port 8080 \
    -t 8 -c 8192 -b 512
```

- `--tensor-split 0.5,0.5` — разделить модель между GPU0 и GPU1 поровну.
- Если карты **разной** памяти (например 12 ГБ + 24 ГБ), делите пропорционально
  ёмкости: `--tensor-split 0.33,0.67`.
- `--parallel 2` — два конвейера обработки запросов (по одному на карту);
  повышает пропускную способность при пакетной обработке. Можно опустить,
  если не нужна максимальная пропускная способность.

Проект уже использует этот подход: основной инстанс (`llama-server`, порт 8080)
запускается на **GPU0+GPU1**, а отдельный (`llama-server-8081`, порт 8081) — на
**GPU1**.

### 6.3. Запуск на одной конкретной карте (например, только GPU1)

Чтобы карта GPU1 стала «нулевой» и модель легла целиком на неё:

```bash
CUDA_VISIBLE_DEVICES=1 /usr/local/bin/llama-server \
    -m /srv/models/модель.Q5_K_M.gguf \
    -ngl 999 \
    --host 0.0.0.0 --port 8081 \
    -t 8 -c 8192 -b 512
```

`CUDA_VISIBLE_DEVICES=1` скрывает GPU0, и GPU1 используется как единственная.

---

## 7. Возможные проблемы

| Признак                                             | Причина и решение |
|-----------------------------------------------------|-------------------|
| `nvcc: command not found`                           | Не установлен CUDA-тулкет (п. 2). Установить или добавить `/usr/local/cuda/bin` в `PATH`. |
| `cuBLAS not found` при сборке                       | Взять режим MMQ: добавить `-DGGML_CUDA_FORCE_MMQ=ON` (п. 4.3). |
| `Unsupported gpu architecture 'sm_XXXX'` при сборке | Неверный номер архитектуры. Поставить правильный из п. 1 (например `86` для RTX 3060). |
| Сборка падает на `-j$(nproc)` по памяти             | Собрать с меньшим числом потоков: `-j4`. |
| `llama-server: error while loading shared libraries: libcuda.so` | Дайрвер не установлен/не тот. `sudo apt install nvidia-driver`, перепидить сервер. |
| Ошибка «out of memory» при запуске модели           | Уменьшить `-ngl` или изменить `--tensor-split` (п. 6). |
| Модель грузится медленно, много в CPU               | `-ngl` слишком мал — увеличить, чтобы больше слоёв легло в VRAM. |

---

## 8. Краткая шпаргалка

**Одна RTX 3060 (sm_86):**

```bash
cmake -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=86
cmake --build build --config Release -j$(nproc)
install -m 0755 build/bin/llama-server /usr/local/bin/llama-server
```

**Две разные RTX (например sm_86 + sm_89):**

```bash
cmake -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=86;89
cmake --build build --config Release -j$(nproc)
install -m 0755 build/bin/llama-server /usr/local/bin/llama-server
```

Запуск на двух картах — `--tensor-split 0.5,0.5 -ngl 999 --parallel 2` (п. 6.2).
