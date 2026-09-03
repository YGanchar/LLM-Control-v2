#!/usr/bin/env bash
# =============================================================================
# run-llama-8081.sh — запуск llama-server для инстанса 8081 (режим 3).
# Модель на GPU1, порт 8081. Используется как отдельный инстанс по требованию.
#
# Переменные модели читаются из /srv/storage/llama-mode-8081.conf (NFS).
# В EXTRA для этого инстанса задаётся -dev 1 и --tensor-split 1 (GPU1).
# =============================================================================
set -o pipefail

CONFIG="/srv/storage/llama-mode-8081.conf"
LLAMA_SERVER="/usr/local/bin/llama-server"

if [ ! -r "$CONFIG" ]; then
    echo "run-llama-8081.sh: конфиг не найден или недоступен: $CONFIG" >&2
    exit 1
fi
if [ ! -x "$LLAMA_SERVER" ]; then
    echo "run-llama-8081.sh: бинарник llama-server не найден: $LLAMA_SERVER" >&2
    exit 1
fi

# shellcheck source=/dev/null
source "$CONFIG"

exec "$LLAMA_SERVER" \
    -m "$MODEL" -t "$THREADS" -c "$CTX" -b "$BATCH" -ngl "$NGL" \
    --host "$HOST" --port "$PORT" $EXTRA
