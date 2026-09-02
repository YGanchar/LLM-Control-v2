# Контекст кодовой базы: LLM-Control-v2

**Сгенерировано:** 2026-08-20 12:17:31
**Точка входа:** `main.py`
**Лимит размера части:** 24 КБ

## 🌳 Структура

```
📁 LLM-Control-v2/
📄 model_scanner.py
📄 server_control.py
📄 ssh_setup.py
📄 system_monitor.py
```

---

## 📦 Содержимое файлов

### Файл: `services/server_control.py`

```py
# server_control.py

import os
import logging
import psutil
from typing import Dict, Optional, List, Any

# Настройка логгера
logger = logging.getLogger(__name__)

class ServerControl:
    def __init__(self) -> None:
        """Инициализация контроллера сервера."""
        pass

    def stop_server(self, pid: Optional[int] = None, timeout: int = 5) -> bool:
        """
        Останавливает сервер Llama.
        
        :param pid: PID процесса для остановки. Если None, ищет по имени 'llama-server'.
        :param timeout: Время ожидания завершения (сек), прежде чем принудительно убить процесс.
        :return: True, если процессы не найдены или успешно остановлены.
        """
        processes_to_stop = []

        if pid is not None:
            try:
                processes_to_stop.append(psutil.Process(pid))
            except psutil.NoSuchProcess:
                logger.warning(f"Процесс с PID {pid} не найден.")
                return True
        else:
            # Поиск всех процессов llama-server
            for proc in psutil.process_iter(['pid', 'cmdline']):
                try:
                    cmdline = proc.info['cmdline']
                    if cmdline and any("llama-server" in arg for arg in cmdline):
                        processes_to_stop.append(proc)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        if not processes_to_stop:
            logger.info("Процессы llama-server не найдены.")
            return True

        for proc in processes_to_stop:
            try:
                logger.info(f"Остановка процесса PID {proc.pid}...")
                proc.terminate()  # SIGTERM
                
                # Ждем завершения, чтобы избежать зомби-процессов
                gone, alive = psutil.wait_procs([proc], timeout=timeout)
                if alive:
                    logger.warning(f"Процесс {proc.pid} не ответил на SIGTERM, используем SIGKILL.")
                    for p in alive:
                        p.kill()  # SIGKILL (принудительно)
                    # Проверить, действительно ли процесс завершился
                    gone2, still_alive = psutil.wait_procs(alive, timeout=2)
                    if still_alive:
                        logger.error(f"Процесс {proc.pid} не завершился даже после SIGKILL")
            except Exception as e:
                logger.error(f"Ошибка при остановке процесса {proc.pid}: {e}")

        return True

    def get_system_stats(self) -> Dict[str, Any]:
        """
        Собирает текущие статистические данные о запущенном сервере Llama.
        """
        stats = {
            "running": False,
            "pid": None,
            "model": None,
            "cpu": 0.0,
            "ram": 0.0
        }

        for proc in psutil.process_iter(['pid', 'cmdline', 'memory_info']):
            try:
                # Проверяем наличие cmdline сразу
                cmdline = proc.info['cmdline']
                if not cmdline or not any("llama-server" in arg for arg in cmdline):
                    continue
                
                stats["running"] = True
                stats["pid"] = proc.info['pid']
                
                # Исправлено: передаем список аргументов напрямую, не склеивая в строку
                stats["model"] = self.extract_model(cmdline)
                
                # RAM (в ГБ)
                stats["ram"] = proc.info['memory_info'].rss / (1024 ** 3)
                
                # CPU: используем системный cpu_percent (без блокировки interval=0.1)
                # Для точных данных о процессе требуется накопительный вызов с интервалом
                stats["cpu"] = psutil.cpu_percent(interval=0)

                break  # Находим только первый процесс сервера
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            except Exception as e:
                logger.error(f"Ошибка при получении данных процесса: {e}")
                continue

        return stats

    def extract_model(self, cmdline_args: List[str], extensions: Optional[List[str]] = None) -> Optional[str]:
        """
        Извлекает имя модели из списка аргументов командной строки.
        Сначала ищет аргумент --model, затем — по расширению.
        Корректно обрабатывает пути с пробелами.
        """
        if extensions is None:
            extensions = [".gguf", ".bin", ".safetensors"]
        
        # Сначала ищем аргумент --model
        for i, arg in enumerate(cmdline_args):
            if arg == "--model" and i + 1 < len(cmdline_args):
                model_arg = cmdline_args[i + 1]
                if any(model_arg.lower().endswith(ext) for ext in extensions):
                    return os.path.basename(model_arg)
        
        # Затем ищем по расширению
        for arg in cmdline_args:
            if any(arg.lower().endswith(ext) for ext in extensions):
                return os.path.basename(arg)
        
        return None

    def is_running(self) -> bool:
        """Проверяет, запущен ли сервер Llama."""
        # Оптимизация: не вызываем get_system_stats целиком, если нам нужно только True/False
        for proc in psutil.process_iter(['cmdline']):
            try:
                cmdline = proc.info['cmdline']
                if cmdline and any("llama-server" in arg for arg in cmdline):
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    def clear(self) -> None:
        """Очистка ресурсов."""
        pass

    def set_model(self, model_path: str) -> None:
        """Установка текущей модели (заглушка)."""
        logger.info(f"Модель установлена на: {model_path}")
```

### Файл: `services/ssh_setup.py`

```py
# services/ssh_setup.py

import os
import subprocess
import logging
from pathlib import Path

class SSHSetupHelper:
    """Помощник для настройки беспарольного SSH-доступа."""
    
    @staticmethod
    def generate_ssh_key(key_type: str = "ed25519", comment: str = "llm-control-key") -> str:
        """Генерирует SSH-ключ без пароля (passphrase empty)."""
        key_path = os.path.expanduser(f"~/.ssh/id_{key_type}_llm")
        
        if os.path.exists(key_path):
            return f"Ключ уже существует: {key_path}"
        
        cmd = [
            "ssh-keygen",
            "-t", key_type,
            "-f", key_path,
            "-N", "",  # Пустой passphrase
            "-C", comment
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logging.info(f"[SSH-Setup] Ключ сгенерирован: {key_path}")
            return f"Ключ сгенерирован: {key_path}"
        except subprocess.CalledProcessError as e:
            logging.error(f"[SSH-Setup] Ошибка генерации ключа: {e}")
            return f"Ошибка: {e.stderr}"
    
    @staticmethod
    def copy_key_to_host(username: str, hostname: str, key_path: str = None) -> str:
        """Копирует публичный ключ на удалённый сервер."""
        if key_path is None:
            key_path = os.path.expanduser("~/.ssh/id_ed25519_llm")
        
        pub_key_path = key_path + ".pub"
        if not os.path.exists(pub_key_path):
            return f"Публичный ключ не найден: {pub_key_path}. Сначала сгенерируйте ключ."
        
        cmd = ["ssh-copy-id", "-i", pub_key_path, f"{username}@{hostname}"]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logging.info(f"[SSH-Setup] Ключ скопирован на {hostname}")
            return "Ключ успешно скопирован на сервер."
        except subprocess.CalledProcessError as e:
            logging.error(f"[SSH-Setup] Ошибка копирования ключа: {e}")
            return f"Ошибка: {e.stderr}"
    
    @staticmethod
    def test_ssh_connection(username: str, hostname: str) -> tuple:
        """Тестирует SSH-подключение без пароля."""
        cmd = [
            "ssh",
            "-o", "ConnectTimeout=5",
            "-o", "StrictHostKeyChecking=no",
            f"{username}@{hostname}",
            "echo 'SSH_TEST_SUCCESS'"
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if "SSH_TEST_SUCCESS" in result.stdout:
                return True, "SSH-подключение работает без пароля."
            else:
                return False, f"Неожиданный вывод: {result.stdout}"
        except subprocess.TimeoutExpired:
            return False, "Таймаут подключения."
        except subprocess.CalledProcessError as e:
            return False, f"Ошибка подключения: {e.stderr}"
        except FileNotFoundError:
            return False, "Команда ssh не найдена в PATH."
    
    @staticmethod
    def get_sudoers_instructions(username: str = "yuri") -> str:
        """Возвращает инструкцию по настройке sudoers."""
        return f"""
Для настройки беспарольного sudo для llmctl, выполните на сервере:

1. Подключитесь к серверу:
   ssh {username}@rtx

2. Отредактируйте sudoers:
   sudo visudo

3. Добавьте строку в конец файла:
   {username} ALL=(ALL) NOPASSWD: /usr/local/bin/llmctl

4. Сохраните и выйдите (Ctrl+O, Enter, Ctrl+X в nano)

Или используйте команду:
   echo '{username} ALL=(ALL) NOPASSWD: /usr/local/bin/llmctl' | sudo tee -a /etc/sudoers.d/llmctl
"""
```

