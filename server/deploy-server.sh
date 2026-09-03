#!/usr/bin/env bash
# =============================================================================
# deploy-server.sh — развёртывание комплекса LLM-Control на сервере.
#
# Устанавливает и настраивает:
#   • /usr/local/bin/llmctl              — оболочка-менеджер инстансов
#   • /usr/local/bin/run-llama.sh        — запуск режима 1 (8080, обе GPU)
#   • /usr/local/bin/run-llama-8081.sh   — запуск режима 3 (8081, GPU1)
#   • /etc/systemd/system/llama-server.service           (режим 1, автостарт)
#   • /etc/systemd/system/llama-server-8081.service      (режим 3, без автостарта)
#   • /etc/sudoers.d/llmctl            — passwordless sudo для llmctl
#
# Применение (один раз, на сервере; пароль запрашивается один раз для элевации):
#   sudo ./deploy-server.sh
#
# Переменные (опционально):
#   PREFIX=/                 — корень, где монтировать (/usr/local, /etc …)
#   SUDO_USER_NAME=yuri      — пользователь сервера для строки sudoers
#   LLAMA_SERVER_BIN=        — путь к бинарнику llama-server (по умолчанию
#                              ${PREFIX}usr/local/bin/llama-server). Если его
#                              нет — скрипт предупредит, но не прервётся.
#   DRY_RUN=1                — только показывать команды, не выполнять
#
# Зависимости, которые СКРИПТ НЕ ставит (см. docs/РАЗВЁРТЫВАНИЕ.md):
#   • NFS-монтирование /srv/storage (конфиги) и /srv/models (модели)
#   • бинарник llama-server (llama.cpp)
# =============================================================================
set -uo pipefail

PREFIX="${PREFIX:-/}"
# Нормализуем PREFIX: добавляем завершающий слэш, кроме корня, чтобы
# «${PREFIX}usr/local/bin» всегда было корректным путём.
if [ "$PREFIX" != "/" ]; then
    case "$PREFIX" in
        */ ) : ;;
        * ) PREFIX="${PREFIX}/" ;;
    esac
fi
LLAMA_USER="${SUDO_USER_NAME:-yuri}"
LLAMA_SERVER_BIN="${LLAMA_SERVER_BIN:-${PREFIX}usr/local/bin/llama-server}"
BIN_DIR="${PREFIX}usr/local/bin"
SYSTEMD_DIR="${PREFIX}etc/systemd/system"
SUDOERS_FILE="${PREFIX}etc/sudoers.d/llmctl"
SUDOERS_DIR="${PREFIX}etc/sudoers.d"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_LLCTL="${SCRIPT_DIR}/llmctl"
SRC_RUN1="${SCRIPT_DIR}/run-llama.sh"
SRC_RUN2="${SCRIPT_DIR}/run-llama-8081.sh"
SRC_SVC1="${SCRIPT_DIR}/llama-server.service"
SRC_SVC2="${SCRIPT_DIR}/llama-server-8081.service"

DRY_RUN="${DRY_RUN:-0}"

log()  { echo "[deploy] $*"; }
warn() { echo "[deploy][warn] $*" >&2; }
die()  { echo "[deploy][error] $*" >&2; exit 1; }

# Выполнить команду (с учётом DRY_RUN).
run() {
    if [ "$DRY_RUN" = "1" ]; then
        echo "[dry-run] $*"
    else
        "$@"
    fi
}

# --- 0. Проверка исходных файлов (лежат рядом со скриптом) --------------------
missing=0
for f in "$SRC_LLCTL" "$SRC_RUN1" "$SRC_RUN2" "$SRC_SVC1" "$SRC_SVC2"; do
    if [ ! -f "$f" ]; then
        warn "не найден исходный файл: $f"
        missing=1
    fi
done
[ "$missing" -eq 1 ] && die "скопируйте всю директорию server/ на сервер (или запустите скрипт из неё)."

# --- 1. Элевация привилегий (один пароль при первом запуске) ------------------
# Целевые каталоги (/usr/local, /etc) требуют root. Тестовый PREFIX (не /) и
# DRY_RUN root не требуют.
SYSTEM_PREFIX=0
case "$PREFIX" in
    ""|"/") SYSTEM_PREFIX=1 ;;
esac

if [ "$DRY_RUN" = "1" ]; then
    log "DRY_RUN=1 — режим просмотра, привилегии не требуются."
elif [ "$SYSTEM_PREFIX" -eq 1 ] && [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        ABS_SCRIPT="$(cd "$SCRIPT_DIR" && pwd)/$(basename "$0")"
        log "Нужны привилегии root — элевация через sudo (пароль спросит один раз)."
        exec sudo env "PREFIX=$PREFIX" "LLAMA_USER=$LLAMA_USER" \
                     "LLAMA_SERVER_BIN=$LLAMA_SERVER_BIN" "DRY_RUN=$DRY_RUN" "$ABS_SCRIPT" "$@"
    fi
    die "Нужны привилегии root. Перезапустите с sudo."
fi

# --- 2. Проверка бинарника llama-server ---------------------------------------
if [ -x "$LLAMA_SERVER_BIN" ]; then
    log "llama-server найден: $LLAMA_SERVER_BIN"
else
    warn "llama-server не найден по пути $LLAMA_SERVER_BIN"
    log "Установите llama-server (llama.cpp) и положите в $LLAMA_SERVER_BIN."
    log "Без него сервисы не запустятся — но остальные компоненты мы настроим."
fi

# --- 3. Установка файлов ------------------------------------------------------
run mkdir -p "$BIN_DIR" "$SYSTEMD_DIR" "$SUDOERS_DIR"

install_file() {  # install_file <src> <dest> <mode>
    run cp -f "$1" "$2"
    run chmod "$3" "$2"
    log "установлено: $2"
}

install_file "$SRC_LLCTL"   "${BIN_DIR}/llmctl"              755
install_file "$SRC_RUN1"    "${BIN_DIR}/run-llama.sh"        755
install_file "$SRC_RUN2"    "${BIN_DIR}/run-llama-8081.sh"   755
install_file "$SRC_SVC1"    "${SYSTEMD_DIR}/llama-server.service"        644
install_file "$SRC_SVC2"    "${SYSTEMD_DIR}/llama-server-8081.service"   644

# --- 4. systemd ---------------------------------------------------------------
# Операции с реальной systemd выполняем только при развёртывании в систему
# (PREFIX=/) и не в режиме просмотра. При тесте в temp-prefix их не трогаем.
if [ "$DRY_RUN" = "1" ]; then
    log "systemd-команды пропущены (DRY_RUN)."
elif [ "$PREFIX" = "/" ] && command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload
    # Режим 1 — основной, включаем в автостарт.
    systemctl enable --now llama-server
    # Режим 3 — только по требованию, автостарт не включаем (но гарантируем off).
    systemctl disable --now llama-server-8081 2>/dev/null || true
    log "systemd-сервисы обновлены."
elif command -v systemctl >/dev/null 2>&1; then
    warn "PREFIX не «/» — systemctl-команды пропущены."
    log "На реальной системе: systemctl daemon-reload && systemctl enable --now llama-server"
fi

# --- 5. passwordless sudo для llmctl ------------------------------------------
sudoers_line="${LLAMA_USER} ALL=(ALL) NOPASSWD: ${BIN_DIR}/llmctl"
if [ -f "$SUDOERS_FILE" ] && grep -qF "$sudoers_line" "$SUDOERS_FILE" 2>/dev/null; then
    log "sudoers уже настроен: $SUDOERS_FILE"
else
    run sh -c "printf '%s\\n' '$sudoers_line' > '$SUDOERS_FILE'"
    run chmod 440 "$SUDOERS_FILE"
    log "passwordless sudo настроен: $sudoers_line"
fi

# --- 6. Проверка ------------------------------------------------------------
if [ "$DRY_RUN" = "1" ]; then
    log "DRY_RUN=1 — проверка установки пропущена (файлы не копились)."
else
    log "проверка установки:"
    if [ -x "${BIN_DIR}/llmctl" ]; then
        log "  llmctl: OK (${BIN_DIR}/llmctl)"
    else
        warn "  llmctl: НЕ установлен"
    fi
    if [ -x "${BIN_DIR}/run-llama.sh" ] && [ -x "${BIN_DIR}/run-llama-8081.sh" ]; then
        log "  run-llama*.sh: OK"
    else
        warn "  run-llama*.sh: НЕ установлены"
    fi
    if [ -f "$SUDOERS_FILE" ]; then
        log "  sudoers: OK ($SUDOERS_FILE)"
    else
        warn "  sudoers: НЕ создан"
    fi

    if [ "$PREFIX" = "/" ] && command -v systemctl >/dev/null 2>&1; then
        systemctl is-enabled llama-server 2>/dev/null || true
    fi
fi

log "Готово. На клиенте теперь доступен беспарольный llmctl через SSH."
log "Проверка с клиента: ssh ${LLAMA_USER}@rtx 'sudo /usr/local/bin/llmctl status'"
