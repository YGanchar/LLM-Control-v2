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