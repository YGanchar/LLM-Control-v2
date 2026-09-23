# Контекст сессии 2026-09-17 (вторая часть)

## Выполненные задачи

### 1. Перемещение проекта
- **LLM-Control-v2** перемещён из `/home/yuri/projects/LLM-Cluster/LLM-Control-v2` в `/home/yuri/projects/LLM-Control-v2`
- Новая структура:
  ```
  ~/projects/
  ├── LLM-Control-v2/          # Основной проект
  │   ├── bot/                 # Telegram бот
  │   ├── server/              # Серверные скрипты
  │   ├── docs/                # Документация
  │   ├── main.py              # Основной файл приложения
  │   └── ...
  ├── LLM-Cluster/             # Старый проект (остался)
  └── ...
  ```

### 2. Telegram бот для управления сервером
**Статус:** Готов к установке

**Созданные файлы:**
```
LLM-Control-v2/bot/
├── llm_server_bot.py          # Основной скрипт бота
├── requirements.txt           # Зависимости (python-telegram-bot)
├── llm-server-bot.service     # systemd сервис
├── setup-bot.sh              # Автоматическая установка
├── README.md                 # Полная документация
└── QUICKSTART.md             # Быстрый старт
```

**Команды бота:**
- `/start` — приветствие
- `/status` — статус сервера (CPU, RAM, GPU, инстансы)
- `/gpu` — детальная информация о GPU
- `/restart` — перезапустить llama-server
- `/stop` — остановить llama-server
- `/logs` — последние 50 строк логов
- `/disk` — информация о диске
- `/ram` — информация о RAM

**Требования для установки:**
1. Создать бота в Telegram через @BotFather → получить токен
2. Узнать свой chat_id через @userinfobot
3. Запустить: `./setup-bot.sh --token TOKEN --chat-id CHAT_ID`

### 3. Мониторинг сервера (из предыдущей сессии)
- `zcode-monitor` — скрипт на сервере rtx для быстрого статуса
- `monitor.sh` — клиентская версия для ZCode
- ZCode skill для автоматического мониторинга

---

## Текущая задача: Загрузка Cold-Fusion-GAIN на сервер

### Найденные файлы

**Модель на сервере:**
```
/srv/models/Qwen3.8-27B-Cold-Fusion-GAIN/Qwen3.8-27B-Cold-Fusion-GAIN-V1.1-NM-DAU-NEO-MAX-NEO-MTP-Q4_K_M.gguf
```
- Размер: **18GB**
- Квантизация: Q4_K_M
- MTP: да (NEO-MAX-NEO-MTP)

**mmproj файл:**
```
/srv/models/Qwen3.8-27B/mmproj-F16.gguf
```
- Размер: 885MB
- Тип: F16

### MOD-файлы (обновлены)

```
/home/yuri/MODS/large/
├── Qwen3.8-27B-Cold-Fusion-GAIN-V1.1-NM-DAU-NEO-MAX-NEO-MTP-Q4_K_M-1x80k-V.mod
└── Qwen3.8-27B-Cold-Fusion-GAIN-V1.1-NM-DAU-NEO-MAX-NEO-MTP-Q4_K_M-1x80k-V-reasoning.mod
```

**Изменения:**
- `tensor-split` исправлен с `72,56` на `60,68` (совпадает с рабочей конфигурацией Salience)

### Текущий статус сервера

**GPU:**
- GPU 0: RTX 3060, 12GB, используется 11.5GB
- GPU 1: RTX 3060, 12GB, используется 11.5GB

**RAM:**
- Total: 62GB
- Used: 12GB
- Free: 17GB

**llama-server (Salience-1.5-Pro):**
- Порт: 8080
- Модель: Salience-1.5-Pro.Q4_K_S (19GB)
- Tensor-split: 60,68
- Контекст: 86016
- Статус: active (running)

**llama-server-8081:**
- Статус: inactive (dead)

### Конфигурация сервера

**/srv/storage/llama-mode.conf** (основной, порт 8080):
```
MODEL="/srv/models/Salience-1.5-Pro.Q4_K_S/Salience-1.5-Pro.Q4_K_S.gguf"
HOST="0.0.0.0"
PORT="8080"
THREADS="6"
CTX="86016"
BATCH="1024"
NGL="999"
EXTRA="--parallel 1 --tensor-split 60,68 --load-mode mlock --temp 0.15 --top-p 0.95 --top-k 20 --min-p 0.0 --repeat-penalty 1.0 -ctk q8_0 -ctv q8_0 --spec-type draft-mtp --spec-draft-n-max 2 --kv-unified -ub 512 -fa on --ctx-checkpoints 16 --cache-ram 16384 --reasoning on --reasoning-budget 4096 --jinja --mmproj /srv/models/Salience-1.5-Pro.Q4_K_S/Salience-1.5-Pro.mmproj-Q8_0.gguf"
```

**/srv/storage/llama-mode-8081.conf** (второй, порт 8081):
```
MODEL="/srv/models/Nemotron-3-Nano-4B-Q6_K_P/Nemotron-3-Nano-4B-Q6_K_P.gguf"
HOST="0.0.0.0"
PORT="8081"
THREADS="4"
CTX="131072"
BATCH="512"
NGL="999"
EXTRA="-dev cuda1 --parallel 2 -sm none --temp 0.7 --top-p 0.95 --top-k 20 --min-p 0.02 --presence-penalty 0.0 --repeat-penalty 1.0 --frequency-penalty 0.0 -ctk q8_0 -ctv q8_0 -fa on --jinja -ub 256 --reasoning off"
```

### SSH-инфраструктура

- **Сервер:** rtx (10.0.0.2), пользователь: yuri
- **Ключ:** `~/.ssh/id_ed25519_llm` (passwordless)
- **GPU:** 2x RTX 3060 (12GB каждая)
- **Порты:** 8080 (основной, autostart), 8081 (второй, ручной)
- **NFS:** `/media/rtx-storage/` ≡ `/srv/storage/`, `/media/rtx-models/` ≡ `/srv/models/`

---

## Нерешённые задачи

### Приоритет 1: Установка Telegram бота
- [ ] Получить токен бота от @BotFather
- [ ] Получить chat_id от @userinfobot
- [ ] Запустить `./setup-bot.sh --token TOKEN --chat-id CHAT_ID`
- [ ] Проверить работу бота (отправить `/start`)

### Приоритет 2: Загрузка Cold-Fusion-GAIN на сервер
- [x] Найти модель на сервере — найдена
- [x] Обновить MOD-файлы (tensor-split)
- [ ] Остановить Salience на rtx
- [ ] Запустить Cold-Fusion-GAIN на порту 8080
- [ ] Протестировать совместимость с mmproj-F16.gguf
- [ ] Создать MOD-файлы для 128k контекста (если нужно)

### Приоритет 3: Локальная модель для тестирования
- [ ] Проверить наличие локальной модели на клиенте
- [ ] При необходимости скачать лёгкую модель
- [ ] Настроить локальный llama-server

---

## Ключевые пути

- **Проект:** `/home/yuri/projects/LLM-Control-v2/`
- **Бот:** `/home/yuri/projects/LLM-Control-v2/bot/`
- **Серверные скрипты:** `/home/yuri/projects/LLM-Control-v2/server/`
- **Документация:** `/home/yuri/projects/LLM-Control-v2/docs/`
- **MOD-файлы:** `/home/yuri/MODS/large/`

---

## Следующие шаги после перезагрузки ZCode

1. Остановить Salience на rtx через SSH
2. Запустить Cold-Fusion-GAIN на порту 8080
3. Протестировать работу зрения
4. Сравнить с Salience-1.5-Pro

---

*Сессия сохранена для продолжения после перезагрузки ZCode.*
