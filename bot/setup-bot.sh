#!/usr/bin/env bash
# =============================================================================
# setup-bot.sh — быстрая установка Telegram-бота для LLM-сервера
#
# Использование:
#   ./setup-bot.sh --token TOKEN --chat-id CHAT_ID
#
# Или интерактивно:
#   ./setup-bot.sh
# =============================================================================

set -e

BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$BOT_DIR/.." && pwd)"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*" >&2; }

# ---------------------------------------------------------------------------
# Парсинг аргументов
# ---------------------------------------------------------------------------

BOT_TOKEN=""
CHAT_ID=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --token)   BOT_TOKEN="$2"; shift 2 ;;
        --chat-id) CHAT_ID="$2"; shift 2 ;;
        *)         error "Неизвестный аргумент: $1"; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Интерактивный ввод, если аргументы не переданы
# ---------------------------------------------------------------------------

if [[ -z "$BOT_TOKEN" ]]; then
    echo ""
    echo -e "${YELLOW}=== Настройка Telegram-бота ===${NC}"
    echo ""
    read -p "Введите токен бота (от @BotFather): " BOT_TOKEN
    read -p "Введите ваш chat_id (от @userinfobot): " CHAT_ID
    echo ""
fi

if [[ -z "$BOT_TOKEN" || -z "$CHAT_ID" ]]; then
    error "Токен и chat_id обязательны!"
    echo ""
    echo "Используйте:"
    echo "  $0 --token TOKEN --chat-id CHAT_ID"
    echo ""
    echo "Или запустите без аргументов для интерактивного режима."
    exit 1
fi

# ---------------------------------------------------------------------------
# Проверка зависимостей
# ---------------------------------------------------------------------------

log "Проверка зависимостей..."

# Python 3
if ! command -v python3 >/dev/null 2>&1; then
    error "Python 3 не найден!"
    exit 1
fi
log "Python 3: $(python3 --version)"

# pip
if ! command -v pip3 >/dev/null 2>&1; then
    error "pip3 не найден!"
    exit 1
fi
log "pip3: $(pip3 --version)"

# ---------------------------------------------------------------------------
# Установка виртуального окружения
# ---------------------------------------------------------------------------

log "Создание виртуального окружения..."

if [[ -d "$BOT_DIR/.venv" ]]; then
    warn "Виртуальное окружение уже существует"
else
    python3 -m venv "$BOT_DIR/.venv"
    log "Виртуальное окружение создано"
fi

# Активируем виртуальное окружение
source "$BOT_DIR/.venv/bin/activate"

# ---------------------------------------------------------------------------
# Установка зависимостей
# ---------------------------------------------------------------------------

log "Установка зависимостей..."

pip install --upgrade pip -q
pip install -r "$BOT_DIR/requirements.txt" -q
log "Зависимости установлены"

# ---------------------------------------------------------------------------
# Настройка systemd-сервиса
# ---------------------------------------------------------------------------

log "Настройка systemd-сервиса..."

SERVICE_FILE="$BOT_DIR/llm-server-bot.service"

if [[ -f "$SERVICE_FILE" ]]; then
    # Заменяем токены в сервис-файле
    sed -i "s/YOUR_BOT_TOKEN/$BOT_TOKEN/g" "$SERVICE_FILE"
    sed -i "s/YOUR_CHAT_ID/$CHAT_ID/g" "$SERVICE_FILE"
    log "Сервис-файл обновлен"

    # Копируем в /etc/systemd/system
    sudo cp "$SERVICE_FILE" /etc/systemd/system/
    log "Сервис скопирован в /etc/systemd/system/"

    # Перезагружаем daemon
    sudo systemctl daemon-reload
    log "systemd daemon перезапущен"

    # Включаем и запускаем сервис
    sudo systemctl enable llm-server-bot
    log "Сервис включен в автозагрузку"

    sudo systemctl start llm-server-bot
    log "Сервис запущен"

    # Проверка статуса
    sleep 2
    if sudo systemctl is-active --quiet llm-server-bot; then
        log "✅ Бот успешно запущен как сервис!"
    else
        warn "⚠️ Бот запущен, но статус неизвестен. Проверьте:"
        echo "  sudo systemctl status llm-server-bot"
        echo "  sudo journalctl -u llm-server-bot -f"
    fi
else
    error "Файл сервиса не найден: $SERVICE_FILE"
    exit 1
fi

# ---------------------------------------------------------------------------
# Финал
# ---------------------------------------------------------------------------

echo ""
echo -e "${GREEN}=== Установка завершена! ===${NC}"
echo ""
echo "🤖 Ваш бот запущен и работает!"
echo ""
echo "📱 Откройте Telegram и найдите вашего бота"
echo "💬 Отправьте /start для начала работы"
echo ""
echo "📋 Доступные команды:"
echo "  /status — текущий статус сервера"
echo "  /gpu    — информация о GPU"
echo "  /restart — перезапустить llama-server"
echo "  /stop   — остановить llama-server"
echo "  /logs   — последние логи"
echo ""
echo "🔧 Управление сервисом:"
echo "  sudo systemctl status llm-server-bot"
echo "  sudo systemctl stop llm-server-bot"
echo "  sudo systemctl start llm-server-bot"
echo "  sudo systemctl restart llm-server-bot"
echo ""
echo "📝 Логи:"
echo "  sudo journalctl -u llm-server-bot -f"
echo ""
