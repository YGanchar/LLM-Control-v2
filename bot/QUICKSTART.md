# 🚀 Быстрый старт — Telegram Bot

## Шаг 1: Создать бота в Telegram (2 минуты)

### 1.1. Создать бота

1. Откройте [@BotFather](https://t.me/BotFather) в Telegram
2. Отправьте `/newbot`
3. Введите имя: `LLM Server Monitor`
4. Введите username: `my_llm_server_bot` (или любой другой)
5. **Скопируйте токен** (строка типа `123456789:ABCdefGHIjklMNOpqrSTUvwxYZ`)

### 1.2. Узнать свой chat_id

1. Откройте [@userinfobot](https://t.me/userinfobot) в Telegram
2. Отправьте `/start`
3. **Скопируйте ваш ID** (числовой, например `123456789`)

---

## Шаг 2: Запустить бота (1 минута)

### Вариант A: Автоматическая установка (рекомендуется)

```bash
cd /home/yuri/projects/LLM-Cluster/LLM-Control-v2/bot
./setup-bot.sh --token ВАШ_ТОКЕН --chat-id ВАШ_CHAT_ID
```

### Вариант B: Интерактивный режим

```bash
cd /home/yuri/projects/LLM-Cluster/LLM-Control-v2/bot
./setup-bot.sh
```

Следуйте подсказкам на экране.

---

## Шаг 3: Проверить работу

1. Откройте Telegram
2. Найдите вашего бота (по username или имени)
3. Отправьте `/start`
4. Должно прийти приветствие со списком команд

---

## 📋 Команды бота

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

---

## 🔧 Управление сервисом

```bash
# Проверить статус
sudo systemctl status llm-server-bot

# Остановить
sudo systemctl stop llm-server-bot

# Запустить
sudo systemctl start llm-server-bot

# Перезапустить
sudo systemctl restart llm-server-bot

# Просмотр логов в реальном времени
sudo journalctl -u llm-server-bot -f
```

---

## ❓ Устранение неполадок

### Бот не отвечает

```bash
# Проверить, запущен ли бот
sudo systemctl status llm-server-bot

# Посмотреть логи
sudo journalctl -u llm-server-bot -f

# Перезапустить
sudo systemctl restart llm-server-bot
```

### Ошибка SSH

Бот использует SSH-ключ `~/.ssh/id_ed25519_llm`. Проверьте:

```bash
# Тест SSH-соединения
ssh -i ~/.ssh/id_ed25519_llm yuri@rtx "echo OK"
```

Если не работает — настройте SSH-ключи (см. docs/РАЗВЁРТЫВАНИЕ.md).

---

## 📚 Подробнее

- [Полная документация](README.md)
- [Документация LLM-Control-v2](../docs/)
- [Архитектура проекта](../docs/ARCHITECTURE_RU.md)
