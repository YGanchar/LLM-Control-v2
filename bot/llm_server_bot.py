#!/usr/bin/env python3
# =============================================================================
# llm_server_bot.py — Telegram-бот для управления LLM-сервером
#
# Команды:
#   /start — приветствие
#   /status — текущий статус сервера
#   /gpu — информация о GPU
#   /restart — перезапустить llama-server
#   /stop — остановить llama-server
#   /logs — последние логи
#   /disk — информация о диске
#   /ram — информация о RAM
#
# Зависимости:
#   pip install python-telegram-bot
#
# Запуск:
#   python llm_server_bot.py --token TOKEN --chat-id CHAT_ID
# =============================================================================

import argparse
import subprocess
import json
import sys
from datetime import datetime

try:
    import telegram
except ImportError:
    print("Ошибка: необходим пакет python-telegram-bot")
    print("Установите: pip install python-telegram-bot")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------

SSH_KEY = "~/.ssh/id_ed25519_llm"
SSH_USER = "yuri"
SSH_HOST = "rtx"
ZCODE_MONITOR = "/home/yuri/bin/zcode-monitor"


# ---------------------------------------------------------------------------
# Утилиты для SSH
# ---------------------------------------------------------------------------

def run_ssh_command(command):
    """Выполнить команду через SSH и вернуть вывод"""
    ssh_cmd = [
        "ssh",
        f"-i {SSH_KEY}",
        f"{SSH_USER}@{SSH_HOST}",
        command
    ]
    try:
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            return f"❌ Ошибка: {result.stderr.strip()}"
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return "❌ Таймаут команды"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"


def get_server_status():
    """Получить полный статус сервера"""
    output = run_ssh_command(ZCODE_MONITOR)
    if not output or output.startswith("❌"):
        return output

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return f"❌ Ошибка парсинга JSON:\n{output}"

    # Форматируем красивый вывод
    lines = []
    lines.append(f"🖥️ **Статус сервера rtx**")
    lines.append(f"⏰ {data['timestamp']}")
    lines.append("")

    # CPU
    cpu = data['cpu']
    lines.append(f"🔧 **CPU:** {cpu['load1']:.2f} / {cpu['load5']:.2f} / {cpu['load15']:.2f}")

    # RAM
    ram = data['ram']
    ram_used_pct = (ram['used_mb'] / ram['total_mb']) * 100
    lines.append(f"💾 **RAM:** {ram['used_mb']} / {ram['total_mb']} MB ({ram_used_pct:.1f}%)")

    # Disk
    disk = data['disk']
    disk_used_pct = ((disk['free_mb'] - disk['free_mb']) / disk['free_mb']) * 100 if disk['free_mb'] > 0 else 0
    # Пересчитаем правильно
    disk_total = 233648  # из предыдущих данных
    disk_used_pct = ((disk_total - disk['free_mb']) / disk_total) * 100
    lines.append(f"💿 **Диск /srv/models:** {disk['free_mb']} MB свободно ({disk_used_pct:.1f}% занято)")

    # GPU
    lines.append("")
    lines.append("🎮 **GPU:**")
    for gpu in data['gpu']:
        gpu_used_pct = (gpu['used_mb'] / gpu['total_mb']) * 100 if gpu['total_mb'] > 0 else 0
        temp_status = "🔥" if gpu['temp_c'] > 80 else "✅"
        vram_status = "⚠️" if gpu_used_pct > 90 else "✅"
        lines.append(
            f"  {temp_status} GPU{gpu['index']}: {gpu['temp_c']}°C | "
            f"{vram_status} VRAM: {gpu['used_mb']} / {gpu['total_mb']} MB ({gpu_used_pct:.1f}%)"
        )

    # Instances
    lines.append("")
    lines.append("🚀 **Инстансы:**")
    for inst in data['instances']:
        status_icon = "✅" if inst['status'] == 'active' else "⏸️"
        lines.append(
            f"  {status_icon} Порт {inst['port']}: PID {inst['pid']} | "
            f"Модель: {inst['model'].split('/')[-1]}"
        )

    # Systemd
    lines.append("")
    systemd = data['systemd']
    lines.append(f"⚙️ **systemd:** 8080={systemd['llama-server-8080']}, 8081={systemd['llama-server-8081']}")

    return "\n".join(lines)


def get_gpu_info():
    """Получить детальную информацию о GPU"""
    output = run_ssh_command("nvidia-smi --query-gpu=index,name,temperature.gpu,memory.used,memory.total --format=csv,noheader")
    if not output or output.startswith("❌"):
        return output

    lines = ["🎮 **Детальная информация о GPU:**"]
    lines.append("")

    for line in output.split('\n'):
        if not line.strip():
            continue
        parts = line.split(',')
        if len(parts) >= 5:
            idx = parts[0].strip()
            name = parts[1].strip()
            temp = parts[2].strip()
            used = parts[3].strip().replace(' MiB', '')
            total = parts[4].strip().replace(' MiB', '')

            used_pct = (int(used) / int(total)) * 100 if int(total) > 0 else 0
            temp_status = "🔥" if int(temp) > 80 else "✅"
            vram_status = "⚠️" if used_pct > 90 else "✅"

            lines.append(f"{temp_status} GPU{idx} ({name}):")
            lines.append(f"  {vram_status} VRAM: {used} / {total} MB ({used_pct:.1f}%)")
            lines.append(f"  🌡️ Температура: {temp}°C")
            lines.append("")

    return "\n".join(lines)


def restart_server(port=""):
    """Перезапустить llama-server"""
    if port:
        cmd = f"sudo /usr/local/bin/llmctl restart {port}"
    else:
        cmd = "sudo /usr/local/bin/llmctl restart"

    output = run_ssh_command(cmd)
    if output.startswith("❌"):
        return output
    return f"✅ Команда отправлена:\n```\n{cmd}\n```\n\nОжидайте 10-15 секунд для перезапуска."


def stop_server(port=""):
    """Остановить llama-server"""
    if port:
        cmd = f"sudo /usr/local/bin/llmctl stop {port}"
    else:
        cmd = "sudo /usr/local/bin/llmctl stop"

    output = run_ssh_command(cmd)
    if output.startswith("❌"):
        return output
    return f"✅ Команда отправлена:\n```\n{cmd}\n```\n\nСервер останавливается."


def get_logs():
    """Получить последние логи"""
    output = run_ssh_command("sudo /usr/local/bin/llmctl logs | tail -50")
    if output.startswith("❌"):
        return output
    if not output:
        return "📝 Логи пусты"

    # Ограничиваем длину сообщения
    if len(output) > 4000:
        output = output[-3990:]
        output = "...\n" + output

    return f"📋 **Последние логи llama-server:**\n```\n{output}\n```"


def get_disk_info():
    """Получить информацию о диске"""
    output = run_ssh_command("df -BM /srv/models")
    if output.startswith("❌"):
        return output

    lines = ["💿 **Информация о диске /srv/models:**"]
    lines.append("")
    lines.append(output)
    return "\n".join(lines)


def get_ram_info():
    """Получить информацию о RAM"""
    output = run_ssh_command("free -m | head -2")
    if output.startswith("❌"):
        return output

    lines = ["💾 **Информация о RAM:**"]
    lines.append("")
    lines.append(output)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Обработчики команд
# ---------------------------------------------------------------------------

def start_command(update, context):
    """Обработчик команды /start"""
    user = update.effective_user
    text = (
        f"👋 Привет, {user.first_name}!\n\n"
        f"Я бот для управления LLM-сервером rtx.\n\n"
        f"📋 **Доступные команды:**\n"
        f"/status — текущий статус сервера\n"
        f"/gpu — информация о GPU\n"
        f"/restart — перезапустить llama-server\n"
        f"/stop — остановить llama-server\n"
        f"/logs — последние логи\n"
        f"/disk — информация о диске\n"
        f"/ram — информация о RAM\n\n"
        f"Используйте /status для быстрого обзора."
    )
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        parse_mode='Markdown'
    )


def status_command(update, context):
    """Обработчик команды /status"""
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="⏳ Загружаю статус сервера...",
        parse_mode='Markdown'
    )

    status = get_server_status()
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=status,
        parse_mode='Markdown'
    )


def gpu_command(update, context):
    """Обработчик команды /gpu"""
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="⏳ Загружаю информацию о GPU...",
        parse_mode='Markdown'
    )

    info = get_gpu_info()
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=info,
        parse_mode='Markdown'
    )


def restart_command(update, context):
    """Обработчик команды /restart"""
    args = context.args
    port = args[0] if args else ""

    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="⏳ Перезапускаю llama-server...",
        parse_mode='Markdown'
    )

    result = restart_server(port)
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=result,
        parse_mode='Markdown'
    )


def stop_command(update, context):
    """Обработчик команды /stop"""
    args = context.args
    port = args[0] if args else ""

    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="⏳ Останавливаю llama-server...",
        parse_mode='Markdown'
    )

    result = stop_server(port)
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=result,
        parse_mode='Markdown'
    )


def logs_command(update, context):
    """Обработчик команды /logs"""
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="⏳ Загружаю логи...",
        parse_mode='Markdown'
    )

    output = get_logs()
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=output,
        parse_mode='Markdown'
    )


def disk_command(update, context):
    """Обработчик команды /disk"""
    output = get_disk_info()
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=output,
        parse_mode='Markdown'
    )


def ram_command(update, context):
    """Обработчик команды /ram"""
    output = get_ram_info()
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=output,
        parse_mode='Markdown'
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='LLM Server Telegram Bot')
    parser.add_argument('--token', required=True, help='Telegram Bot API token')
    parser.add_argument('--chat-id', required=True, help='Your Telegram chat ID')
    args = parser.parse_args()

    # Создаем бота
    bot = telegram.Bot(token=args.token)

    # Проверяем права бота
    try:
        bot.get_me()
        print("✅ Бот успешно авторизован")
    except Exception as e:
        print(f"❌ Ошибка авторизации: {e}")
        sys.exit(1)

    # Создаем updater и dispatcher
    updater = telegram.Updater(token=args.token, use_context=True)
    dp = updater.dispatcher

    # Регистрируем обработчики команд
    dp.add_handler(telegram.ext.CommandHandler('start', start_command))
    dp.add_handler(telegram.ext.CommandHandler('status', status_command))
    dp.add_handler(telegram.ext.CommandHandler('gpu', gpu_command))
    dp.add_handler(telegram.ext.CommandHandler('restart', restart_command))
    dp.add_handler(telegram.ext.CommandHandler('stop', stop_command))
    dp.add_handler(telegram.ext.CommandHandler('logs', logs_command))
    dp.add_handler(telegram.ext.CommandHandler('disk', disk_command))
    dp.add_handler(telegram.ext.CommandHandler('ram', ram_command))

    # Запускаем бота
    print("🤖 Бот запущен. Ожидание сообщений...")
    print(f"💡 Ваш chat_id: {args.chat_id}")
    print("📱 Отправьте /start в Telegram для начала работы")

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
