# LLM-Control v2 — Архитектура и руководство разработчика

> Русская версия: этот файл. English: [ARCHITECTURE.md](ARCHITECTURE.md)

## 1. Что это такое

**LLM-Control v2** — лёгкий GUI-пульт управления инстансами `llama-server` на удалённой GPU-машине. Это **тонкий клиент**: приложение само не запускает инференс и не загружает модели. Оно пишет конфиги, управляет systemd-сервисами через `llmctl` по SSH и собирает метрики из `/proc` и `nvidia-smi`.

Типовая схема: бесшумная рабочая станция + GPU-сервер в углу (headless). Пульт живёт на рабочей станции, инференс — на сервере, движок — стоковый `llama-server` из llama.cpp.

```
РАБОЧАЯ СТАНЦИЯ (клиент)                      GPU-СЕРВЕР (headless)
┌─────────────────────────────┐               ┌────────────────────────────────┐
│ LLM-Control-v2 (PySide6)    │               │ llama-server :8080 (systemd)   │
│                             │               │ llama-server :8081 (systemd)   │
│ QProcess + ssh ─────────────┼── sudo ───────┼► /usr/local/bin/llmctl         │
│                             │               │   └─ systemctl {start|stop|    │
│ RemoteMonitorThread ────────┼── SSH ────────┼► /proc, nvidia-smi, pgrep      │
│ (paramiko, опрос 2 с)       │               │                                │
│                             │               │ /srv/storage/llama-mode.conf   │
│ /media/rtx-storage/*.conf ◄─┼─── NFS ───────┼─ (конфиги читает systemd-юнит) │
│ ~/.ssh/id_ed25519_llm       │               │ WoL: Magic Packet UDP:9        │
└─────────────────────────────┘               └────────────────────────────────┘
```

## 2. Карта модулей

| Модуль | Ответственность |
|---|---|
| `main.py` | Точка входа: разрешение пути `.env` (внешний приоритетнее вшитого), логирование, SIGTERM/SIGINT → штатный выход |
| `main_ui.py` | `MainWindow`: три вкладки, статус-бар, разводка сигналов монитора, `retranslate_ui`, `closeEvent` (гасит стрим логов и поток мониторинга) |
| `scanner_widget.py` | Сканер `.gguf`: рекурсивный обход, таблица (имя/размер/vision), выбор языка, `WrappingBar` (собственная переносящаяся раскладка) |
| `config_widget.py` | Пресеты `.mod`: сканирование каталога MODS, подбор пресета к модели по префиксу имени, автогенератор конфига (таблицы CTX/BATCH/NGL по кванту и размеру) |
| `server_widget.py` | Пульт сервера: радио 8080/8081, команды `llmctl` через QProcess+ssh, редактор конфига с валидатором, WoL/poweroff, стрим `journalctl -f` |
| `locale_manager.py` | `LocaleManager` (синглтон `locale`): JSON-словари, fallback на `en` |
| `services/system_monitor.py` | `RemoteMonitorThread` (QThread + paramiko): CPU/RAM/GPU/VRAM, сопоставление процессов портам, self-healing, WoL, `poweroff` |
| `services/ssh_manager.py` | Поиск и кэширование SSH-ключа, сборка аргументов для внешнего `ssh` |
| `services/ssh_setup.py` | Помощник первичной настройки: `ssh-keygen`, `ssh-copy-id`, инструкция sudoers |
| `services/model_scanner.py` | Итеративный поиск файлов по расширению (`os.scandir`, без рекурсии) |
| `services/mod_generator.py` | Автономная CLI-утилита (GUI не использует): маппинг клиентского пути в серверный `/srv/models/...` |
| `services/server_control.py` | Пустая заглушка совместимости импорта |

## 3. Потоки и обмен данными

**Поток GUI** — все виджеты. Сканирование дисков выполняется синхронно в этом потоке (осознанное упрощение, см. «Ограничения»).

**RemoteMonitorThread (QThread)** — цикл опроса каждые 2 секунды:
1. `cat /proc/stat` → CPU (дельта между опросами), `cat /proc/meminfo` → RAM;
2. `pgrep -af llama-server` + разбор `--port` в cmdline → какие инстансы живы и какой PID у какого порта;
3. `nvidia-smi --query-gpu=...` → VRAM/питание по картам;
4. `nvidia-smi --query-compute-apps=...` → VRAM по PID → разносится по портам инстансов.

Самовосстановление: 3 сбоя подряд → принудительный реконнект; keepalive SSH 10 с; флаг `planned_shutdown` глушит шум после намеренного `poweroff`. Остановка — `stop()` из `closeEvent`, `wait(3000)` → `terminate()`.

**Управляющие команды** — по QProcess на команду: `ssh -i <ключ> <хост> sudo /usr/local/bin/llmctl <действие>[ 8081]`. Вывод пишется в лог-панель по `readyReadStandardOutput/StandardError`. Стрим логов (`journalctl -f`) хранится в `current_stream_process` и терминируется перед новой командой и при закрытии окна.

**Сигналы** (Qt): `metrics_received` (монитор → статус-бар), `scan_started/scan_finished/model_selected` (сканер → main_ui → конфиг), `run_command_requested` (конфиг → пульт сервера), `language_changed` (сканер → `retranslate_ui`), `shutdown_status_received/wol_status_received` (монитор → лог-панель).

## 4. Конфигурационные файлы

| Файл | Назначение |
|---|---|
| `.env` (рядом с бинарем/скриптом) | Все настройки: пути, SSH, MAC, язык, ширина окна, последние выборы. Полный список — `.env.example` |
| `.env`, вшитый в сборку | Fallback, если внешнего нет (см. §5) |
| `model_layers.json` | Имя модели → число слоёв (для ограничения NGL в автогенераторе) |
| `locales/{ru,en,es}.json` | Плоские словари «ключ → строка». Наборы ключей всех языков должны совпадать |
| `*.mod` (каталог MODS) | Пресеты запуска в dotenv-стиле: `MODEL/HOST/PORT/THREADS/CTX/BATCH/NGL/EXTRA`; многострочный `EXTRA` с `\` поддерживается |
| `llama-mode.conf` / `llama-mode-8081.conf` | Рабочие конфиги сервера. Пишутся пультом в NFS-путь `/media/rtx-storage/` (на сервере — `/srv/storage/`), читаются systemd-юнитами при старте `llama-server` |

## 5. Правила разрешения `.env` (контракт)

- **Из исходников**: `.env` рядом с `main.py`.
- **Frozen (PyInstaller onefile)**: `.env` **рядом с бинарем** — высший приоритет; вшитый в бинарник (`_MEIPASS/.env`) используется только если внешнего нет.
- Причина: `load_dotenv` по умолчанию **не переопределяет** уже установленные переменные, поэтому порядок загрузки критичен. `main.py` грузит внешний первым; `__file__` в frozen-режиме указывает внутрь `_MEIPASS` и для поиска внешнего `.env` использоваться не должен.

## 6. Локализация

- `LocaleManager.translate(key)` возвращает строку по ключу; ключа нет → возвращается сам ключ (без fallback-словаря). Отсюда правило: **ключ добавляется во все три JSON одновременно**.
- Каждый виджет реализует `retranslate()`; `MainWindow.retranslate_ui()` разводит его по вкладкам и статус-бару (последние метрики накладываются поверх заполнителей).
- Стабильная геометрия: `_sync_stable_sizes()` в сканере берёт максимум `sizeHint` по всем локалям (`_all_locale_texts`) — смена языка не двигает раскладку.
- Добавить язык: создать `locales/xx.json` со всеми ключами + пару `("xx", "config.lang_xx")` в `_populate_language_combo` (scanner_widget.py).

## 7. Валидатор конфига (`server_widget._validate_config`)

Проверки перед записью конфига на NFS: обязательные ключи (`MODEL/PORT/CTX/NGL`), диапазон PORT, CTX ≥ 8, NGL > 0 или `auto`, отсутствие пробела перед `\` в многострочном `EXTRA` (аргументы слипнутся), и комбинация `NGL="auto"` + ручной `--tensor-split` — уже приводила к OOM при старте. Строки `INFO:` вычищаются при сохранении.

## 8. Сборка и развёртывание

```bash
# окружение
python -m venv .venv
.venv/bin/pip install -r requirements.txt

# проверки
.venv/bin/python -m py_compile main.py main_ui.py scanner_widget.py \
    config_widget.py server_widget.py locale_manager.py services/*.py

# сборка onefile (бандлит locales/, model_layers.json, .env)
.venv/bin/pyinstaller --noconfirm LLM-Control-v2.spec
# результат: dist/LLM-Control-v2

# развёртывание: скопировать бинарь в каталог приложения, рядом держать .env
cp dist/LLM-Control-v2 /path/to/appdir/
```

Серверная часть (`server/`): `llmctl` → `/usr/local/bin/llmctl`; `/etc/sudoers.d/llmctl` с `NOPASSWD` для `llmctl`; юниты `llama-server.service` (автостарт, порт 8080) и `llama-server-8081.service`. Подробно — `docs/DEPLOYMENT.md` / `docs/РАЗВЁРТЫВАНИЕ.md`.

## 9. Smoke-тест без дисплея

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python - <<'PY'
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
app = QApplication(sys.argv)
from main_ui import MainWindow
w = MainWindow(); w.show()
QTimer.singleShot(1500, w.close)   # closeEvent: стрим + монитор
sys.exit(app.exec())
PY
```

Для frozen-бинаря — то же, плюс проверка в логе строки `.env загружен из <каталог бинаря>/.env` (не `_MEI...`).

## 10. Конвенции кода

- `_resolve_env_path()` повторяется в каждом UI-модули намеренно (одинаковый контракт frozen/скрипт) — не заменять на относительный `".env"`.
- Пользовательские строки — только через `locale.translate('ключ.подключ')`; хардкод в коде = баг.
- Связь виджетов — через сигналы, не прямыми ссылками вверх (исключение — `parent_widget` для диалогов).
- Остановка фоновых процессов: стрим логов и монитор гасятся в `MainWindow.closeEvent`; QProcess не убивает дочерний процесс сам — только явный `terminate()`.
- Логи: префиксы `[MAIN]`, `[MAIN_UI]`, `[SW]`, `[CW]`, `[Monitor]`, `[SSHManager]`, `[LOCALE]`.

## 11. Известные ограничения

- Сканирование (`/media/rtx-models`, каталог MODS) — синхронное, в потоке GUI: на больших/NFS-каталогах окно замирает (в коде помечено; кандидат на QThread).
- Клиент — только Linux; для управления используется системный `ssh` и `paramiko`.
- Инструмент для личной/LAN-сети: авторизация — только SSH-ключи, HTTP-эндпоинтов у пульта нет.
- Таблицы автоподбора NGL/CTX рассчитаны на одну карту; для мульти-GPU конфиг правится вручную.
