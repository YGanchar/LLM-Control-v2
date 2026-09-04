# AGENTS.md — инструкции для ИИ-агентов (ZCode и др.)

Проект: **LLM-Control v2** — PySide6 GUI-пульт управления llama-server на удалённой GPU-машине по SSH.

## Быстрые команды

```bash
# Запуск из исходников (только из каталога проекта)
.venv/bin/python main.py

# Проверка синтаксиса (минимум перед любым коммитом)
.venv/bin/python -m py_compile main.py main_ui.py scanner_widget.py \
    config_widget.py server_widget.py locale_manager.py services/*.py

# Smoke-тест GUI без дисплея (см. docs/ARCHITECTURE_RU.md, §9)
QT_QPA_PLATFORM=offscreen .venv/bin/python - <<'PY'
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
app = QApplication(sys.argv)
from main_ui import MainWindow
w = MainWindow(); w.show()
QTimer.singleShot(1500, w.close)   # closeEvent: стрим логов + монитор
sys.exit(app.exec())
PY

# Сборка onefile (бандлит locales/, model_layers.json, .env)
.venv/bin/pyinstaller --noconfirm LLM-Control-v2.spec   # результат: dist/LLM-Control-v2
```

## Структура (коротко)

- `main.py` — вход; разрешение `.env` (внешний рядом с бинарем/скриптом приоритетнее вшитого).
- `main_ui.py` — `MainWindow`: 3 вкладки, статус-бар, `closeEvent` гасит стрим логов и поток мониторинга.
- `scanner_widget.py` / `config_widget.py` / `server_widget.py` — вкладки Сканер / Параметры / Сервер.
- `locale_manager.py` + `locales/{ru,en,es}.json` — локализация.
- `services/` — `system_monitor` (QThread+paramiko), `ssh_manager`, `ssh_setup`, `model_scanner`, `mod_generator` (автономная утилита), `server_control` (пустая заглушка).
- `server/` — серверная часть: `llmctl`, systemd-юниты, deploy-скрипт.
- Подробная архитектура: `docs/ARCHITECTURE_RU.md` (EN: `docs/ARCHITECTURE.md`).

## Конвенции (нарушать нельзя)

1. **Любые пользовательские строки — только `locale.translate('ключ.подключ')`.**
   Хардкод строк в коде = баг. Новый ключ добавляется **одновременно во все три**
   `locales/*.json` (наборы ключей обязаны совпадать; `translate` не имеет
   fallback-словаря и вернёт сырой ключ).
2. **`.env` ищется через `_resolve_env_path()`** (у каждого UI-модуля своя копия
   паттерна) — никогда не использовать относительный `".env"`: `set_key` молча
   создаст файл в cwd процесса.
3. **Коммиты и комментарии в коде — на русском.** Стиль коммита: короткий
   префикс (`UI:`, `Сканер:`, `Конфиг:`, `Сборка:` или область) + суть; в теле —
   что и почему. Версионированные фиксы — с номерами пунктов аудита, если есть.
4. **Фоновые процессы гасятся явно** в `MainWindow.closeEvent`
   (`control_widget.stop_current_stream()` + `system_monitor.stop()`).
   QProcess не убивает дочерний процесс при уничтожении объекта.
5. Связь виджетов — через сигналы, не прямыми ссылками вверх.
6. Клиент — только Linux; проверять что-либо через `QT_QPA_PLATFORM=offscreen`,
   реальный X-сервер для тестов не нужен.

## Приватность

- `.env` содержит реальные хосты/MAC — в `.gitignore`, в коммит не попадает
  (проверка: `git check-ignore .env`).
- `git add` — только конкретные файлы, **никогда `git add -A`/`git add .`**.
- Push — только по явной команде пользователя.
- Рабочие скриншоты с приватным — в `/home/yuri/projects/LLM-Cluster/_private/`
  (приватная папка разработчика, вне репозитория).

## Известные особенности

- Синхронное сканирование моделей блокирует GUI-поток (осознанное упрощение,
  кандидат в QThread — см. «Известные ограничения» в ARCHITECTURE).
- Валидатор конфига `_validate_config` кодифицирует реальные OOM-грабли
  (`NGL=auto` + `--tensor-split`, пробел перед `\` в многострочном `EXTRA`) —
  не ослаблять проверки без веской причины.
- В frozen-сборке `__file__` указывает внутрь `_MEIPASS` — для поиска внешних
  файлов использовать `sys.executable` (см. `main.py`).
