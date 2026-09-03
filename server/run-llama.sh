#!/usr/bin/env bash
# =============================================================================
# run-llama.sh — запуск llama-server для инстанса 8080 (режим 1).
# Большая модель на обеих GPU (GPU0+GPU1), порт 8080.
# Вызывается systemd-сервисом llama-server.service.
#
# Переменные модели (MODEL HOST PORT THREADS CTX BATCH NGL EXTRA) читаются
# из конфига /srv/storage/llama-mode.conf (NFS, редактируется с клиента).
# =============================================================================
set -o pipefail

CONFIG="/srv/storage/llama-mode.conf"
LLAMA_SERVER="/usr/local/bin/llama-server"

if [ ! -r "$CONFIG" ]; then
    echo "run-llama.sh: конфиг не найден или недоступен: $CONFIG" >&2
    exit 1
fi
if [ ! -x "$LLAMA_SERVER" ]; then
    echo "run-llama.sh: бинарник llama-server не найден: $LLAMA_SERVER" >&2
    exit 1
fi

# Импортируем переменные из конфига. Строки вида KEY=VALUE без кавычек
# безопасно выполняются shell'ю через source.
# shellcheck source=/dev/null
source "$CONFIG"

exec "$LLAMA_SERVER" \
    -m "$MODEL" -t "$THREADS" -c "$CTX" -b "$BATCH" -ngl "$NGL" \
    --host "$HOST" --port "$PORT" $EXTRA
