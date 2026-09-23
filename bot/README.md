# Telegram Bot для управления LLM-сервером

Бот позволяет управлять LLM-сервером rtx через Telegram.

## 📋 Команды

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие и список команд |
| `/status` | Текущий статус сервера (CPU, RAM, GPU, инстансы) |
| `/gpu` | Детальная информация о GPU |
| `/restart` | Перезапустить llama-server |
| `/stop` | Остановить llama-server |
| `/logs` | Последние 50 строк логов |
| `/disk` | Информация о диске /srv/models |
| `/ram` | Информация о RAM |

## 🚀 Установка

### 1. Создание бота в Telegram

1. Откройте [@BotFather](https://t.me/BotFather)
2. Отправьте `/newbot`
3. Следуйте инструкциям и скопируйте **токен**
4. Откройте [@userinfobot](https://t.me/userinfobot) и скопируйте ваш **ID**

### 2. Установка зависимостей

```bash
cd /home/yuri/projects/LLM-Cluster/LLM-Control-v2/bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Запуск (ручной)

```bash
cd /home/yuri/projects/LLM-Cluster/LLM-Control-v2/bot
source .venv/bin/activate
python llm_server_bot.py --token YOUR_BOT_TOKEN --chat-id YOUR_CHAT_ID
```

### 4. Запуск как сервис (автозапуск)

```bash
# Отредактируйте сервис
nano /home/yuri/projects/LLM-Cluster/LLM-Control-v2/bot/llm-server-bot.service

# Замените YOUR_BOT_TOKEN и YOUR_CHAT_ID на реальные значения

# Установите сервис
sudo cp /home/yuri/projects/LLM-Cluster/LLM-Control-v2/bot/llm-server-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable llm-server-bot
sudo systemctl start llm-server-bot

# Проверка статуса
sudo systemctl status llm-server-bot
```

## 🔧 Настройка

### Переменные окружения (опционально)

Если хотите изменить путь к SSH-ключу или хост, отредактируйте файл `llm_server_bot.py`:

```python
SSH_KEY = "~/.ssh/id_ed25519_llm"
SSH_USER = "yuri"
SSH_HOST = "rtx"
```

## 🛠️ Устранение неполадок

### Бот не отвечает

1. Проверьте, запущен ли бот:
   ```bash
   ps aux | grep llm_server_bot
   ```

2. Проверьте логи сервиса:
   ```bash
   sudo journalctl -u llm-server-bot -f
   ```

3. Проверьте токен бота:
   - Откройте [@BotFather](https://t.me/BotFather)
   - Отправьте `/mybots`
   - Выберите вашего бота и проверьте токен

### Ошибки SSH

Бот использует SSH-ключ `~/.ssh/id_ed25519_llm`. Убедитесь, что:
- Ключ существует и имеет правильные права (`chmod 600`)
- Публичный ключ добавлен в `~/.ssh/authorized_keys` на сервере rtx
- SSH-соединение работает без пароля:
  ```bash
  ssh -i ~/.ssh/id_ed25519_llm yuri@rtx "echo OK"
  ```

## 📝 Примеры использования

### Быстрый статус

```
Вы: /status
Бот: 🖥️ Статус сервера rtx
     ⏰ 2026-09-17T09:11:17Z
     
     🔧 CPU: 0.44 / 0.60 / 0.46
     💾 RAM: 9453 / 64249 MB (14.7%)
     💿 Диск /srv/models: 36648 MB свободно (84.3% занято)
     
     🎮 GPU:
     ✅ GPU0: 61°C | ✅ VRAM: 11669 / 12288 MB (95.0%)
     ✅ GPU1: 54°C | ✅ VRAM: 11728 / 12288 MB (95.5%)
     
     🚀 Инстансы:
     ✅ Порт 8080: PID 51956 | Модель: Salience-1.5-Pro.Q4_K_S.gguf
     
     ⚙️ systemd: 8080=active, 8081=inactive
```

### Перезапуск сервера

```
Вы: /restart
Бот: ⏳ Перезапускаю llama-server...
     ✅ Команда отправлена:
     ```
     sudo /usr/local/bin/llmctl restart
     ```
     
     Ожидайте 10-15 секунд для перезапуска.
```

## 🔒 Безопасность

- Бот работает от имени пользователя `yuri`
- SSH-ключ имеет ограниченные привилегии (только llmctl через sudoers)
- Токен бота хранится в командной строке (не в файле)
- Для продакшена рекомендуется использовать переменные окружения

## 📚 Дополнительные ресурсы

- [Telegram Bot API](https://core.telegram.org/bots/api)
- [python-telegram-bot docs](https://python-telegram-bot.org/)
- [LLM-Control-v2 documentation](../docs/)
