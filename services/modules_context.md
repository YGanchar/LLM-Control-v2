# Контекст кодовой базы: services

**Сгенерировано:** 2026-08-20 14:17:15
**Режим:** Сбор всех файлов без анализа импортов

## 🌳 Структура

```
📁 services/
```

---

## 📦 Содержимое файлов

### Файл: `__init__.py`

```py

```

### Файл: `mod_generator.py`

```py
"""
mod_generator.py

Модуль для генерации .mod-файлов для удалённого RTX-сервера.
Учитывает реальный путь модели на клиенте (/media/rtx-models/...)
и преобразует его в серверный (/srv/models/...).
"""

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class EnvConfig:
    last_scan_path: Path
    last_mods_path: Path
    llama_path: Optional[Path]
    ssh_host: Optional[str]
    default_config_path: Optional[Path]
    client_models_root: Path
    server_models_root: Path

def load_env(env_path: str | Path = ".env") -> EnvConfig:
    env_path = Path(env_path)
    if env_path.exists():
        load_dotenv(env_path)

    # Используем .absolute() вместо .resolve(), чтобы не "улетать" за пределы 
    # логической структуры из-за симлинков при проверке путей
    last_scan_path = Path(os.getenv("LAST_SCAN_PATH", "/media/rtx-models")).expanduser().absolute()
    last_mods_path = Path(os.getenv("LAST_MODS_PATH", "/home/yuri/MODS/")).expanduser().absolute()
    llama_path = os.getenv("LLAMA_PATH")
    ssh_host = os.getenv("SSH_HOST")
    default_config_path = os.getenv("DEFAULT_CONFIG_PATH")

    # Корни путей должны быть абсолютными для корректного сравнения
    client_models_root = Path("/media/rtx-models").absolute()
    server_models_root = Path("/srv/models").absolute()

    return EnvConfig(
        last_scan_path=last_scan_path,
        last_mods_path=last_mods_path,
        llama_path=Path(llama_path) if llama_path else None,
        ssh_host=ssh_host,
        default_config_path=Path(default_config_path) if default_config_path else None,
        client_models_root=client_models_root,
        server_models_root=server_models_root,
    )

@dataclass
class ModParams:
    threads: int = 4
    ctx: int = 32768
    batch: int = 320
    ngl: int = 60
    host: str = "0.0.0.0"
    port: int = 8080
    extra: str = ""

    def validate(self):
        """Проверка параметров перед сохранением."""
        if self.threads <= 0: raise ValueError("Threads must be > 0")
        if not (1 <= self.port <= 65535): raise ValueError("Invalid port range")
        if self.ctx < 8: raise ValueError("Context size too small")

def to_server_model_path(client_model_path: Path, cfg: EnvConfig) -> Path:
    """Преобразует клиентский путь в серверный."""
    # Используем absolute(), чтобы сохранить логическую структуру симлинков
    abs_client_path = client_model_path.expanduser().absolute()

    try:
        rel = abs_client_path.relative_to(cfg.client_models_root)
        return (cfg.server_models_root / rel).resolve() # Здесь resolve уместен для финального пути
    except ValueError:
        logger.warning(f"Path {abs_client_path} is not under client root {cfg.client_models_root}")
        return abs_client_path

def infer_model_name_from_path(model_path: Path) -> str:
    """Извлекает имя модели, корректно обрабатывая файлы в корне."""
    # Если путь — это файл прямо в корне моделей, берем его stem
    if model_path.parent == client_models_root_fallback(): # (см. рекомендации ниже)
        return model_path.stem

    parent = model_path.parent.name
    stem = model_path.stem

    # Список "технических" папок, которые не являются именами моделей
    ignored_dirs = {"_todo", "models", "gguf", "rtx-models"} 
    
    if parent and parent not in ignored_dirs:
        return parent
    return stem

def client_models_root_fallback():
    # Вспомогательная функция для логики в infer_model_name
    return Path("/media/rtx-models")

def build_mod_content(server_model_path: Path, params: ModParams) -> str:
    """Формирует содержимое .mod файла."""
    return (
        f'MODEL="{str(server_model_path)}"\n'
        f'HOST="{params.host}"\n'
        f'PORT="{params.port}"\n\n'
        f'THREADS="{params.threads}"\n\n'
        f'CTX="{params.ctx}"\n'
        f'BATCH="{params.batch}"\n'
        f'NGL="{params.ngl}"\n\n'
        f'EXTRA="{params.extra}"\n'
    )

def save_mod_file(content: str, cfg: EnvConfig, model_name: str, suffix: Optional[str] = None) -> Path:
    mods_dir = cfg.last_mods_path.expanduser()
    mods_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{model_name}_{suffix}.mod" if suffix else f"{model_name}.mod"
    mod_path = mods_dir / filename
    
    try:
        mod_path.write_text(content, encoding="utf-8")
        return mod_path
    except OSError as e:
        logger.error(f"Failed to save file {mod_path}: {e}")
        raise

def generate_mod_for_client_model(
    client_model_path: str | Path,
    env_path: str | Path = ".env",
    params: Optional[ModParams] = None,
    suffix: Optional[str] = None,
) -> Path:
    cfg = load_env(env_path)
    if params is None:
        params = ModParams()
    else:
        params.validate()

    client_model_path = Path(client_model_path).absolute()
    server_model_path = to_server_model_path(client_model_path, cfg)
    
    # Исправленная логика получения имени
    if client_model_path.parent == cfg.client_models_root:
        model_name = client_model_path.stem
    else:
        model_name = infer_model_name_from_path(server_model_path)

    content = build_mod_content(server_model_path, params)
    return save_mod_file(content, cfg, model_name, suffix=suffix)

if __name__ == "__main__":
    # Тест
    try:
        example_client_path = "/media/rtx-models/NVIDIA-Nemotron-3-Nano-4B-Q8_0/model.gguf"
        mod_file = generate_mod_for_client_model(example_client_path)
        print(f"Успех! Создан файл: {mod_file}")
    except Exception as e:
        print(f"Ошибка при генерации: {e}")
```

### Файл: `model_scanner.py`

```py
# services/model_scanner.py

import os
from typing import List, Tuple, Generator

def _scan_directory(scan_path: str, extension: str) -> Generator[Tuple[str, int, float], None, None]:
    """
    Общий итеративный обход директории для поиска файлов с заданным расширением.
    """
    if not os.path.isdir(scan_path):
        raise ValueError(f"Invalid directory: {scan_path}")

    ext = extension.lower().strip()
    if ext and not ext.startswith('.'):
        ext = f".{ext}"

    stack = [scan_path]
    while stack:
        current_dir = stack.pop()
        try:
            with os.scandir(current_dir) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            if entry.name.lower().endswith(ext):
                                stat_info = entry.stat()
                                yield (entry.path, stat_info.st_size, stat_info.st_mtime)
                    except (OSError, PermissionError):
                        continue
        except (OSError, PermissionError):
            continue

def find_files_by_extension(scan_path: str, extension: str) -> List[Tuple[str, int, float]]:
    """
    Сканирует директорию на наличие файлов с заданным расширением.
    """
    return list(_scan_directory(scan_path, extension))

def find_files_generator(scan_path: str, extension: str) -> Generator[Tuple[str, int, float], None, None]:
    """
    Версия-генератор для работы с очень большими дисками.
    Позволяет получать файлы по одному, не загружая всё в память.
    """
    return _scan_directory(scan_path, extension)
```

### Файл: `server_control.py`

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

### Файл: `ssh_setup.py`

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

### Файл: `system_monitor.py`

```py
# services/system_monitor.py
import os
import socket
import logging
import subprocess
import paramiko
import re
from typing import Optional
from dotenv import load_dotenv
from PySide6.QtCore import QThread, Signal

DEFAULT_HOST = "10.0.0.2"
DEFAULT_USER = "yuri"
DEFAULT_MAC = "44:8A:5B:5E:79:88"
SSH_TIMEOUT = 5
UPDATE_INTERVAL_MS = 2000

# Порты инстансов, за которыми следим. Первый - всегда автостартующий (llama-server.service),
# второй - опциональный ручной запуск на второй карте.
KNOWN_PORTS = (8080, 8081)


class RemoteMonitorThread(QThread):
    metrics_received = Signal(dict)
    shutdown_status_received = Signal(str)
    wol_status_received = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        load_dotenv()
        self.host = os.getenv("SERVER_HOST", DEFAULT_HOST)
        self.user = os.getenv("SERVER_USER", DEFAULT_USER)
        self.mac = os.getenv("SERVER_MAC", DEFAULT_MAC)
        self.running = True
        self.ssh = None
        self.planned_shutdown = False
        self.consecutive_failures = 0  # Счётчик для принудительного реконнекта
        self._prev_cpu = None  # Для расчёта CPU через /proc/stat
        
        # Поиск SSH-ключа
        self.ssh_key_path = self._find_ssh_key()
        if not self.ssh_key_path:
            logging.warning(
                "[Monitor] SSH-ключ не найден. Беспарольный доступ не работает. "
                "Выполните: ssh-keygen -t ed25519 && ssh-copy-id yuri@rtx"
            )

    def _find_ssh_key(self) -> Optional[str]:
        """Ищет первый доступный SSH-ключ из списка вариантов."""
        key_paths = [
            "~/.ssh/id_ed25519_llm",  # Специальный ключ для LLM-Control
            "~/.ssh/id_ed25519",       # Стандартный Ed25519
            "~/.ssh/id_rsa",           # Стандартный RSA
        ]
        for kp in key_paths:
            expanded = os.path.expanduser(kp)
            if os.path.exists(expanded):
                return expanded
        return None

    def _safe_float(self, value_str: str, default: float = 0.0) -> float:
        if not value_str:
            return default
        try:
            cleaned = re.sub(r'[^\d.]', '', value_str.replace(',', '.'))
            return float(cleaned)
        except ValueError:
            return default

    def _connect_ssh(self) -> bool:
        try:
            if self.ssh:
                self.ssh.close()
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # Загружаем SSH-ключ
            pkey = None
            if self.ssh_key_path:
                try:
                    pkey = paramiko.Ed25519Key.from_private_key_file(self.ssh_key_path)
                except Exception as e:
                    logging.warning(f"[Monitor] Не удалось загрузить ключ {self.ssh_key_path}: {e}")
            else:
                logging.error("[Monitor] Нет SSH-ключа для подключения.")

            self.ssh.connect(
                hostname=self.host,
                username=self.user,
                pkey=pkey,
                timeout=SSH_TIMEOUT,
                look_for_keys=False,   # отключаем автопоиск, чтобы не путаться
                allow_agent=False
            )

            # Keepalive: каждые 10 секунд шлём пульс, чтобы "полумёртвые" сессии обнаруживались
            self.ssh.get_transport().set_keepalive(10)
            return True
        except Exception as e:
            if not self.planned_shutdown:
                logging.error(f"[Monitor] Ошибка подключения к {self.host}: {e}")
            return False

    def _exec(self, cmd: str, timeout: int = 5) -> str:
        """Выполняет команду и гарантированно закрывает канал."""
        _, stdout, _ = self.ssh.exec_command(cmd, timeout=timeout)
        try:
            return stdout.read().decode('utf-8', errors='ignore')
        finally:
            stdout.channel.close()

    def run(self) -> None:
        logging.info(f"[Monitor] Поток мониторинга запущен для хоста {self.host}")
        while self.running:
            # Сбрасываем planned_shutdown, если сервер снова доступен
            if self.planned_shutdown and self._is_port_open(self.host, 22):
                self.planned_shutdown = False
                logging.info("[Monitor] Сервер снова доступен, возобновляю мониторинг.")

            stats = {
                "system": {"cpu": 0.0, "ram": 0.0},
                "instances": {port: {"running": False, "pid": None, "vram_gb": 0.0} for port in KNOWN_PORTS},
                "gpu": []  # список {"index":.., "used_gb":.., "total_gb":.., "power_w":..}
            }

            is_connected = False
            if self.ssh and self.ssh.get_transport() and self.ssh.get_transport().is_active():
                is_connected = True
            elif not self.planned_shutdown:
                is_connected = self._connect_ssh()

            if is_connected and not self.planned_shutdown:
                # Самовосстановление: после 3 сбоев подряд принудительно пересоздаём соединение
                if self.consecutive_failures >= 3:
                    logging.warning("[Monitor] 3 сбоя подряд — принудительно пересоздаю соединение.")
                    try:
                        if self.ssh:
                            self.ssh.close()
                    except Exception:
                        pass
                    self.ssh = None
                    self.consecutive_failures = 0
                    is_connected = self._connect_ssh()

                if is_connected:
                    try:
                        # 1. Сбор метрик CPU и RAM
                        # 1. Сбор метрик CPU и RAM через /proc для надёжности
                        proc_stat = self._exec("cat /proc/stat")
                        meminfo = self._exec("cat /proc/meminfo")
                        
                        # Парсинг CPU из /proc/stat
                        if proc_stat and self._prev_cpu is not None:
                            cpu_line = [l for l in proc_stat.splitlines() if l.startswith('cpu ')]
                            if cpu_line:
                                parts = cpu_line[0].split()
                                if len(parts) >= 8:
                                    try:
                                        curr = list(map(int, parts[1:]))
                                        prev = self._prev_cpu
                                        curr_total = sum(curr)
                                        prev_total = sum(prev)
                                        curr_idle = curr[3] + (curr[4] if len(curr) > 4 else 0)
                                        prev_idle = prev[3] + (prev[4] if len(prev) > 4 else 0)
                                        
                                        total_diff = curr_total - prev_total
                                        idle_diff = curr_idle - prev_idle
                                        
                                        if total_diff > 0:
                                            cpu_usage = 100.0 * (1.0 - idle_diff / total_diff)
                                            stats["system"]["cpu"] = max(0.0, min(100.0, cpu_usage))
                                        self._prev_cpu = curr
                                    except Exception as e:
                                        logging.debug(f"[Monitor] Ошибка расчёта CPU: {e}")
                        elif proc_stat:
                            cpu_line = [l for l in proc_stat.splitlines() if l.startswith('cpu ')]
                            if cpu_line:
                                parts = cpu_line[0].split()
                                if len(parts) >= 8:
                                    try:
                                        self._prev_cpu = list(map(int, parts[1:]))
                                    except Exception:
                                        pass
                        
                        # Парсинг RAM из /proc/meminfo
                        if meminfo:
                            mem_total = None
                            mem_available = None
                            for line in meminfo.splitlines():
                                if line.startswith('MemTotal:'):
                                    mem_total = self._safe_float(line.split()[1], default=None)
                                elif line.startswith('MemAvailable:'):
                                    mem_available = self._safe_float(line.split()[1], default=None)
                                elif mem_available is None and line.startswith('MemFree:'):
                                    mem_free = self._safe_float(line.split()[1], default=None)
                                    if mem_free is not None:
                                        mem_available = mem_free
                            
                            if mem_total and mem_total > 0 and mem_available is not None:
                                used_percent = 100.0 * (1.0 - mem_available / mem_total)
                                stats["system"]["ram"] = max(0.0, min(100.0, used_percent))
                            else:
                                logging.debug("[Monitor] Не удалось получить данные RAM из /proc/meminfo")

                        # 2. Процессы llama-server (с портами из cmdline)
                        proc_part = self._exec("pgrep -af llama-server")
                        port_by_pid = {}
                        for line in proc_part.strip().splitlines():
                            line = line.strip()
                            if not line or not line.split(" ", 1)[0].isdigit():
                                continue
                            pid_str, _, cmdline = line.partition(" ")
                            port_match = re.search(r'--port[= ](\d+)', cmdline)
                            if port_match:
                                port = int(port_match.group(1))
                                port_by_pid[int(pid_str)] = port
                                if port in stats["instances"]:
                                    stats["instances"][port]["running"] = True
                                    stats["instances"][port]["pid"] = int(pid_str)

                        # 3. VRAM/питание по каждой карте целиком - отдельным запросом,
                        # без склейки с другими командами (надёжнее парсить)
                        gpu_part = self._exec(
                            "nvidia-smi --query-gpu=index,memory.used,memory.total,power.draw "
                            "--format=csv,noheader,nounits"
                        )
                        for line in gpu_part.strip().splitlines():
                            parts = [p.strip() for p in line.split(',')]
                            if len(parts) >= 4:
                                stats["gpu"].append({
                                    "index": int(self._safe_float(parts[0])),
                                    "used_gb": self._safe_float(parts[1]) / 1024.0,
                                    "total_gb": self._safe_float(parts[2], default=12288.0) / 1024.0,
                                    "power_w": int(self._safe_float(parts[3])),
                                })
                        if len(stats["gpu"]) < 2:
                            logging.warning(
                                f"[Monitor] Ожидалось 2 GPU в выводе nvidia-smi, получено "
                                f"{len(stats['gpu'])}. Сырой вывод: {gpu_part!r}"
                            )

                        # 4. VRAM по каждому процессу - отдельным запросом, разносим между
                        # инстансами по портам (полученным из pgrep выше)
                        apps_part = self._exec(
                            "nvidia-smi --query-compute-apps=pid,used_memory "
                            "--format=csv,noheader,nounits"
                        )
                        for line in apps_part.strip().splitlines():
                            parts = [p.strip() for p in line.split(',')]
                            if len(parts) >= 2:
                                pid = int(self._safe_float(parts[0]))
                                mem_gb = self._safe_float(parts[1]) / 1024.0
                                port = port_by_pid.get(pid)
                                if port in stats["instances"]:
                                    stats["instances"][port]["vram_gb"] += mem_gb

                        # Дошли до конца без исключений — соединение здоровое, сбрасываем счётчик
                        self.consecutive_failures = 0

                    except Exception as e:
                        if not self.planned_shutdown:
                            self.consecutive_failures += 1
                            logging.error(f"[Monitor] Ошибка сбора данных ({self.consecutive_failures}): {e}")
            else:
                # В режиме запланированного отключения при закрытом порте просто ждём,
                # planned_shutdown НЕ сбрасываем.
                pass

            self.metrics_received.emit(stats)
            self.msleep(UPDATE_INTERVAL_MS)

    def _is_port_open(self, host: str, port: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            return False

    def send_wake_on_lan(self) -> None:
        logging.info(f"[Monitor] Попытка отправки WoL на MAC: {self.mac}...")
        self.planned_shutdown = False
        try:
            clean_mac = self.mac.replace(":", "").replace("-", "")
            if len(clean_mac) != 12:
                raise ValueError("Неверный формат MAC-адреса")
            hex_data = bytes.fromhex("FF" * 6 + clean_mac * 16)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(hex_data, ('255.255.255.255', 9))
            sock.close()
            logging.info("[Monitor] Magic Packet успешно направлен")
            self.wol_status_received.emit("Magic Packet успешно отправлен (broadcast)")
        except Exception as e:
            logging.error(f"[Monitor] Ошибка WoL: {e}")
            for cmd in [["wakeonlan", self.mac], ["etherwake", self.mac]]:
                try:
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self.wol_status_received.emit(f"Пакет отправлен через {cmd[0]}")
                    break
                except OSError:
                    continue

    def shutdown_host(self) -> None:
        if not self.ssh or not self.ssh.get_transport() or not self.ssh.get_transport().is_active():
            logging.warning("[Monitor] Нет активного SSH-соединения для выключения.")
            return
        logging.info(f"[Monitor] Инициализация выключения сервера {self.host}...")
        self.planned_shutdown = True
        self.shutdown_status_received.emit("Отправка команды на выключение питания...")
        try:
            self.ssh.exec_command("sudo poweroff", timeout=2)
        except Exception as e:
            logging.info(f"[Monitor] Команда отправлена, соединение разрывается: {e}")
        finally:
            if self.ssh:
                self.ssh.close()

    def stop(self) -> None:
        self.running = False
        if self.ssh:
            try:
                self.ssh.close()
            except Exception:
                pass
        self.wait()
```

