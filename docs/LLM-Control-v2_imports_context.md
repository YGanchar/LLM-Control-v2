# Context Export
Project: /home/yuri/projects/LLM-Cluster/LLM-Control-v2
Mode: imports
Files: 10
main.py — 2771 bytes
main_ui.py — 9979 bytes
services/system_monitor.py — 16539 bytes
services/server_control.py — 1346 bytes
services/ssh_manager.py — 4513 bytes
scanner_widget.py — 10030 bytes
services/model_scanner.py — 1965 bytes
config_widget.py — 22031 bytes
server_widget.py — 22574 bytes
services/ssh_setup.py — 4191 bytes

# main.py
# main.py
import sys
import os
import logging
from PySide6.QtWidgets import QApplication, QMessageBox

# Настройка логирования (выполняется до импорта тяжелых модулей, force=True переопределяет все предыдущие handlers)
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    force=True
)
logging.getLogger("paramiko").setLevel(logging.WARNING)

def load_environment(base_dir):
    """Загрузка переменных окружения из .env файла."""
    env_path = os.path.join(base_dir, ".env")
    if os.path.exists(env_path):
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
            logging.info(f"[MAIN] .env загружен из {env_path}.")
            return True
        except ImportError:
            logging.warning("[MAIN] Библиотека 'python-dotenv' не установлена.")
        except Exception as e:
            logging.error(f"[MAIN] Ошибка при загрузке .env: {e}")
    else:
        logging.warning(f"[MAIN] Файл .env не найден по пути {env_path}.")
    return False

def main():
    # Определяем базовую директорию приложения
    base_dir = os.path.dirname(os.path.abspath(__file__))
    logging.info(f"[MAIN] Запуск приложения. Директория: {base_dir}")

    load_environment(base_dir)

    app = QApplication(sys.argv)

    try:
        # Импорт внутри try, чтобы перехватить ошибки отсутствующих зависимостей UI
        from main_ui import MainWindow
        main_window = MainWindow()
        main_window.show()
    except ImportError as e:
        error_msg = f"Критическая ошибка импорта модулей интерфейса:\n{e}"
        logging.critical(f"[MAIN] {error_msg}")
        # Показываем окно ошибки пользователю, прежде чем закрыться
        QMessageBox.critical(None, "Ошибка запуска", error_msg)
        sys.exit(1)
    except Exception as e:
        error_msg = f"Непредвиденная ошибка при запуске:\n{e}"
        logging.exception("[MAIN] Ошибка") # exception запишет traceback в лог
        QMessageBox.critical(None, "Ошибка", error_msg)
        sys.exit(1)

    # В PySide6 рекомендуется использовать sys.exit(app.exec()) 
    # для корректного завершения процесса при закрытии окна
    sys.exit(app.exec())

if __name__ == '__main__':
    main()

# main_ui.py
# main_ui.py

import logging
import os
import sys
from typing import List, Any, Dict, Optional

from dotenv import set_key, load_dotenv
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTabWidget
)
from PySide6.QtGui import QFont, QCloseEvent  # QCloseEvent перенесен в QtGui
from PySide6.QtCore import QTimer, Signal

def _resolve_env_path() -> str:
    """.env рядом с исполняемым файлом (frozen-сборка) или со скриптом (Thonny/venv)."""
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, ".env")

# Загружаем конфигурацию из .env
_env_path = _resolve_env_path()
if os.path.exists(_env_path):
    load_dotenv(_env_path)

from services.system_monitor import RemoteMonitorThread
from services.server_control import ServerControl
from scanner_widget import ScannerWidget
from config_widget import ConfigWidget
from server_widget import ServerControlWidget

class MainWindow(QMainWindow):
    system_usage_updated = Signal(dict)   # Сигнал без жестких типов данных

    def __init__(self) -> None:
        super().__init__()

        # 1. Инициализируем фоновые сервисы и запускаем поток мониторинга (один раз)
        self.system_monitor: Optional[RemoteMonitorThread] = RemoteMonitorThread()
        self.system_monitor.start()
        self.server_control: ServerControl = ServerControl()

        # Настройки главного окна
        self.setWindowTitle("LLM-Control BY")
        self.setGeometry(100, 100, 900, 720)

        # Главный контейнер
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        # Инициализируем вкладки
        self.tab_widget = QTabWidget()
        self.main_layout.addWidget(self.tab_widget)

        # Таб 1: Сканер моделей
        self.scanner_tab = QWidget()
        self.scanner_tab_layout = QVBoxLayout(self.scanner_tab)
        self.scanner_widget = ScannerWidget(self)
        self.scanner_tab_layout.addWidget(self.scanner_widget)
        self.tab_widget.addTab(self.scanner_tab, "Сканер Моделей")

        # Таб 2: Параметры модели
        self.config_tab = QWidget()
        self.config_tab_layout = QVBoxLayout(self.config_tab)
        self.config_widget = ConfigWidget(self)
        self.config_tab_layout.addWidget(self.config_widget)
        self.tab_widget.addTab(self.config_tab, "Параметры модели")

        # Таб 3: Управление сервером
        self.control_tab = QWidget()
        self.control_tab_layout = QVBoxLayout(self.control_tab)
        
        # Важно: создаем ServerControlWidget
        self.control_widget = ServerControlWidget(self)
        self.control_tab_layout.addWidget(self.control_widget)
        self.tab_widget.addTab(self.control_tab, "Сервер RTX")

        # 2. Передаем запущенный поток мониторинга внутрь созданного виджета сервера
        self.control_widget.set_monitor_thread(self.system_monitor)

        # Нижняя информационная строка статус-бара
        self.system_info_layout = QHBoxLayout()
        font = QFont("DejaVu Sans Mono", 10)

        self.cpu_label = QLabel("SRV CPU: --")
        self.ram_label = QLabel("SRV RAM: --")
        self.llama_label = QLabel("8080: CONNECTING...")
        self.llama2_label = QLabel("8081: --")
        self.gpu_label = QLabel("GPU0/1: --")

        for label in (self.cpu_label, self.ram_label, self.llama_label, self.llama2_label, self.gpu_label):
            label.setFont(font)

        self.cpu_label.setFixedWidth(130)
        self.ram_label.setFixedWidth(130)
        self.llama_label.setFixedWidth(230)
        self.llama2_label.setFixedWidth(230)
        self.gpu_label.setFixedWidth(420)

        self.system_info_layout.addWidget(self.cpu_label)
        self.system_info_layout.addSpacing(20)
        self.system_info_layout.addWidget(self.ram_label)
        self.system_info_layout.addSpacing(30)
        self.system_info_layout.addWidget(self.llama_label)
        self.system_info_layout.addSpacing(10)
        self.system_info_layout.addWidget(self.llama2_label)
        self.system_info_layout.addSpacing(30)
        self.system_info_layout.addWidget(self.gpu_label)
        self.system_info_layout.addStretch()

        # Добавляем строку статуса в самый низ главного окна
        self.main_layout.addLayout(self.system_info_layout)

        self._init_metrics_labels()
        self._connect_signals()
        # По умолчанию открываем вкладку «Параметры модели» — там работа с пресетами
        self.tab_widget.setCurrentIndex(1)

    def _setup_timers(self) -> None:
        self.system_update_timer = QTimer(self)
        self.system_update_timer.setInterval(2000)
        self.system_update_timer.timeout.connect(self._update_system_metrics)
        self.system_update_timer.start()

    def _connect_signals(self) -> None:
        # Подключаем обработку полученных метрик от RemoteMonitorThread к интерфейсу главного окна
        if self.system_monitor:
            self.system_monitor.metrics_received.connect(self._handle_metrics_update)

        # События от встроенных виджетов
        self.scanner_widget.scan_started.connect(self._on_scan_started)
        self.scanner_widget.scan_finished.connect(self._on_scan_finished)
        self.scanner_widget.model_selected.connect(self._on_model_selected)
        self.config_widget.run_command_requested.connect(self._on_command_requested)

    def _on_command_requested(self, command_string: str) -> None:
        """Обработка конфигурационной команды, полученной из ConfigWidget."""
        logging.info(f"[MAIN_UI] Получена команда от ConfigWidget: {command_string}")
        self.tab_widget.setCurrentWidget(self.control_tab)
        self.control_widget.update_command_display(command_string)

    def _save_settings(self) -> None:
        try:
            last_scan_path = self.scanner_widget.current_scan_path
            last_save_path = self.scanner_widget.current_save_path
            set_key(".env", "LAST_SCAN_PATH", last_scan_path)
            set_key(".env", "LAST_SAVE_PATH", last_save_path)
            logging.info("[MAIN_UI] Настройки успешно сохранены.")
        except Exception as e:
            logging.error(f"[MAIN_UI] Ошибка сохранения настроек: {e}")

    def _on_scan_started(self) -> None:
        logging.info("[MAIN_UI] Сканирование началось...")

    def _on_scan_finished(self, models: List[str]) -> None:
        logging.info(f"[MAIN_UI] Сканирование завершено. Найдено моделей: {len(models)}")

    def closeEvent(self, event: QCloseEvent) -> None:
        logging.info("[MAIN_UI] Закрытие приложения...")

        # Безопасная остановка и дожидание завершения потока мониторинга
        if hasattr(self, 'system_monitor') and self.system_monitor and self.system_monitor.isRunning():
            logging.info("[MAIN_UI] Остановка потока мониторинга...")
            self.system_monitor.stop()
            if not self.system_monitor.wait(3000):
                logging.warning("[MAIN_UI] Поток не ответил на запрос остановки, завершаем принудительно.")
                self.system_monitor.terminate()
                self.system_monitor.wait()

        self._save_settings()
        event.accept()

    def _init_metrics_labels(self) -> None:
        self.metrics_labels: Dict[str, QLabel] = {
            'cpu': self.cpu_label,
            'ram': self.ram_label,
        }

    def _handle_metrics_update(self, stats: Dict[str, Any]) -> None:
        try:
            system = stats["system"]
            instances = stats.get("instances", {})
            gpus = stats.get("gpu", [])

            self.cpu_label.setText(f"SRV CPU: {system['cpu']:.1f}%")
            self.ram_label.setText(f"SRV RAM: {system['ram']:.1f}%")

            inst_8080 = instances.get(8080, {})
            if inst_8080.get("running"):
                self.llama_label.setText(f"8080: ACTIVE | {inst_8080.get('vram_gb', 0.0):.2f} GB")
            else:
                self.llama_label.setText("8080: OFFLINE")

            inst_8081 = instances.get(8081, {})
            if inst_8081.get("running"):
                self.llama2_label.setText(f"8081: ACTIVE | {inst_8081.get('vram_gb', 0.0):.2f} GB")
            else:
                self.llama2_label.setText("8081: OFFLINE")

            if gpus:
                parts = [f"GPU{g['index']}: {g['used_gb']:.1f}/{g['total_gb']:.1f}GB {g['power_w']}W" for g in gpus]
                self.gpu_label.setText(" | ".join(parts))
            else:
                self.gpu_label.setText("GPU: --")
        except Exception as e:
            logging.error(f"[MAIN_UI] Ошибка отображения метрик: {e}")

    def _on_model_selected(self, full_path: str, size_gb: float) -> None:
        logging.info(f"[MAIN_UI] Выбрана модель: {os.path.basename(full_path)}")
        self.tab_widget.setCurrentWidget(self.config_tab)
        self.config_widget.set_model(full_path, size_gb)

# services/system_monitor.py
# -*- coding: utf-8 -*-
import os
import socket
import logging
import subprocess
import paramiko
import re
from typing import Optional
from dotenv import load_dotenv
from PySide6.QtCore import QThread, Signal

from services.ssh_manager import SSHManager

DEFAULT_HOST = "10.0.0.2"
DEFAULT_USER = "yuri"
DEFAULT_MAC = "44:8A:5B:5E:79:88"
SSH_TIMEOUT = 5
UPDATE_INTERVAL_MS = 2000

# Порты инстансов, за которыми следим. Первый - всегда автостартующий
# (llama-server.service), второй - опциональный ручной запуск на второй карте.
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

        # Поиск SSH-ключа — делегируем единому менеджеру
        self.ssh_key_path = SSHManager.get_ssh_key_path()
        if not self.ssh_key_path:
            logging.warning(
                "[Monitor] SSH-ключ не найден. Беспарольный доступ не работает. "
                "Выполните: ssh-keygen -t ed25519 && ssh-copy-id yuri@rtx"
            )

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
                        # Точечная проверка: на сервере с двумя 3060 ожидаем 2 карты.
                        # Если меньше — карта пропала (драйвер, отказ), показываем сырой вывод.
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

# services/server_control.py
# server_control.py

import logging

# Настройка логгера
logger = logging.getLogger(__name__)


class ServerControl:
    """Минимальная заглушка для обратной совместимости импорта.

    Все методы класса (stop_server, get_system_stats, extract_model,
    is_running, clear, set_model) ранее были мёртвыми кодом — ни один из них
    не вызывался нигде. Функциональность, которую они дублировали, реализована
    в services/system_monitor.py (RemoteMonitorThread: процессы llama-server,
    метрики, извлечение модели) и в server_widget.py/llmctl (остановка сервера).

    main_ui.py создаёт объект только ради импорта:
        self.server_control: ServerControl = ServerControl()
    Поэтому оставляем пустой __init__, чтобы не ломать сборку.

    Если понадобится локальный контроль процессов на основе psutil — дописать
    методы заново.
    """

    def __init__(self) -> None:
        """Инициализация контроллера сервера."""
        pass

# services/ssh_manager.py
# -*- coding: utf-8 -*-
"""
Единый менеджер SSH-ключей для проекта LLM-Control.

Выносит общую логику поиска и кэширования SSH-ключа из
system_monitor.py и server_widget.py в одно место (DRY).
"""
import os
import logging
from typing import List, Optional


class SSHManager:
    """
    Синглтон-подобный менеджер SSH-подключений.

    Отвечает за:
    - поиск первый доступный SSH-ключа из списка кандидатов;
    - кэширование найденного пути (чтобы не проверять os.path.exists
      при каждом клике по кнопке);
    - формирование аргументов командной строки для внешнего ssh-клиента
      (QProcess) и для paramiko.
    """

    _cached_key_path: Optional[str] = None
    _key_searched: bool = False

    # Кандидаты на SSH-ключ — от специфичного к общему.
    # Специальный ключ LLM-Control идёт первым, чтобы не конфликтовать
    # с пользовательскими ключами, если они есть.
    _KEY_CANDIDATES: List[str] = [
        "~/.ssh/id_ed25519_llm",  # Специальный ключ для LLM-Control
        "~/.ssh/id_ed25519",       # Стандартный Ed25519
        "~/.ssh/id_rsa",           # Стандартный RSA
    ]

    @classmethod
    def get_ssh_key_path(cls) -> Optional[str]:
        """
        Ищет и кэчирует первый доступный SSH-ключ.

        Возвращает абсолютный путь к ключу или None, если ни один
        из кандидатов не найден. Повторные вызовы возвращают
        закэшированное значение без повторного обращения к ФС.
        """
        if cls._key_searched:
            return cls._cached_key_path

        for kp in cls._KEY_CANDIDATES:
            expanded = os.path.expanduser(kp)
            if os.path.exists(expanded):
                cls._cached_key_path = expanded
                cls._key_searched = True
                logging.info(f"[SSHManager] Найден SSH-ключ: {expanded}")
                return expanded

        cls._key_searched = True
        cls._cached_key_path = None
        logging.warning(
            "[SSHManager] SSH-ключ не найден ни по одному из путей: "
            f"{cls._KEY_CANDIDATES}. "
            "Беспарольный доступ не работает. "
            "Выполните: ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_llm -N '' "
            "&& ssh-copy-id -i ~/.ssh/id_ed25519_llm.pub yuri@rtx"
        )
        return None

    @classmethod
    def get_ssh_base_args(cls, host: str, command: str) -> List[str]:
        """
        Формирует базовые аргументы для запуска внешнего ssh-клиента
        через QProcess.

        Args:
            host: имя хоста или IP (должен резолвиться через ~/.ssh/config
                  или /etc/hosts).
            command: команда, которую нужно выполнить на удалённом хосте.

        Returns:
            Список аргументов для QProcess.start("ssh", args).
            Пустой список, если SSH-ключ не найден (вызывающий код
            должен сам показать диалог настройки).
        """
        key = cls.get_ssh_key_path()
        if not key:
            return []

        return [
            "-i", key,
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=5",
            host,
            command,
        ]

    @classmethod
    def reset_cache(cls) -> None:
        """
        Сбрасывает кэш ключа. Полезно после генерации нового ключа
        через SSHSetupHelper — чтобы следующий вызов get_ssh_key_path()
        увидел свежий файл.
        """
        cls._cached_key_path = None
        cls._key_searched = False
        logging.info("[SSHManager] Кэш SSH-ключа сброшен.")

# scanner_widget.py
# scanner_widget.py
# -*- coding: utf-8 -*-
import os
import logging
from typing import List, Tuple

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QLabel, QLineEdit, QFileDialog, QHeaderView,
    QProgressBar, QSizePolicy, QMessageBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont

# Предполагаем наличие этого модуля в проекте
try:
    from services.model_scanner import find_files_by_extension
except ImportError:
    logging.error("Модуль services.model_scanner не найден")
    def find_files_by_extension(*args): return []

class ScannerWidget(QWidget):
    scan_started = Signal()
    scan_finished = Signal(list)  # List[Tuple[str, float]] - (путь, размер)
    model_selected = Signal(str, float)   # (путь, размер) 
 
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_widget = parent
        self.current_scan_path = os.getenv("LAST_SCAN_PATH") or ""
        self.current_save_path = os.getenv("LAST_SAVE_PATH") or ""
        self.llama_path = os.getenv("LLAMA_PATH") or ""
        
        # Структура данных: [(full_path, size_gb, has_vision_bool), ...]
        self.models_data: List[Tuple[str, float, bool]] = []
        self._sort_states: dict = {}  # {column_index: ascending_bool}
        self._init_ui()

    def _init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)

        # Панель выбора пути
        self.scan_path_layout = QHBoxLayout()
        self.scan_path_label = QLabel("Путь сканирования:")
        self.scan_path_edit = QLineEdit(self.current_scan_path)
        self.scan_path_edit.setReadOnly(True)

        self.browse_button = QPushButton("Обзор...")
        self.browse_button.clicked.connect(self._browse_directory)

        self.scan_path_layout.addWidget(self.scan_path_label)
        self.scan_path_layout.addWidget(self.scan_path_edit)
        self.scan_path_layout.addWidget(self.browse_button)
        self.layout.addLayout(self.scan_path_layout)

        # Кнопки управления
        self.control_buttons_layout = QHBoxLayout()
        self.scan_button = QPushButton("Сканировать")
        self.scan_button.clicked.connect(self.start_scan)
        self.save_button = QPushButton("Сохранить список")
        self.save_button.clicked.connect(self.save_sorted_list)

        self.control_buttons_layout.addWidget(self.scan_button)
        self.control_buttons_layout.addWidget(self.save_button)
        self.control_buttons_layout.addStretch()
        self.layout.addLayout(self.control_buttons_layout)

        # Прогресс-бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.layout.addWidget(self.progress_bar)

        # Таблица
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(3)
        self.table_widget.setHorizontalHeaderLabels(["Имя модели", "Размер (GB)", "Vision"])
        self.table_widget.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_widget.setSelectionMode(QTableWidget.SingleSelection)
        
        # Настройка колонок
        header = self.table_widget.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        
        self.table_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.layout.addWidget(self.table_widget)

        # Сигналы таблицы
        header.sectionClicked.connect(self.sort_by_column)
        self.table_widget.itemDoubleClicked.connect(self.on_model_double_clicked)

    def _browse_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Выбрать директорию для сканирования", self.current_scan_path)
        if directory:
            self.current_scan_path = directory
            self.scan_path_edit.setText(self.current_scan_path)

    def start_scan(self):
        if not self.current_scan_path or not os.path.isdir(self.current_scan_path):
            QMessageBox.warning(self, "Ошибка", "Выбранный путь не существует или недоступен.")
            return

        self.scan_started.emit()
        self._set_ui_enabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.table_widget.setRowCount(0)

        try:
            # В реальном приложении здесь лучше использовать QThread!
            raw_files = find_files_by_extension(self.current_scan_path, ".gguf")
            
            vision_directories = set()
            for file_path, _, _ in raw_files:
                filename_lower = os.path.basename(file_path).lower()
                if any(x in filename_lower for x in ["mmproj", "clip-", "vision"]):
                    vision_directories.add(os.path.dirname(file_path))

            processed_models = []
            for file_path, size_bytes, _ in raw_files:
                filename_lower = os.path.basename(file_path).lower()
                if any(x in filename_lower for x in ["mmproj", "clip-", "vision"]):
                    continue
                    
                size_gb = size_bytes / (1024 ** 3)
                has_vision = os.path.dirname(file_path) in vision_directories
                processed_models.append((file_path, size_gb, has_vision))

            self.models_data = processed_models
            logging.info(f"[Сканер] Найдено: {len(processed_models)}")

            # Уведомляем другие части приложения (legacy support)
            legacy_list = [(p, s) for p, s, _ in self.models_data]
            self.scan_finished.emit(legacy_list)
            
            self._populate_table(self.models_data)
            self.progress_bar.setValue(100)
            
        except Exception as e:
            logging.error(f"Ошибка сканирования: {e}")
            QMessageBox.critical(self, "Ошибка", f"Произошла ошибка при сканировании:\n{str(e)}")
        finally:
            self._set_ui_enabled(True)
            self.progress_bar.setVisible(False)

    def _set_ui_enabled(self, enabled: bool):
        """Вспомогательный метод для управления состоянием кнопок"""
        self.scan_button.setEnabled(enabled)
        self.browse_button.setEnabled(enabled)

    def _populate_table(self, models: List[Tuple[str, float, bool]]):
        self.table_widget.setRowCount(len(models))
        green_brush = QBrush(QColor("#27ae60"))
        bold_font = QFont()
        bold_font.setBold(True)

        for row_index, (file_path, size_gb, has_vision) in enumerate(models):
            # Имя модели
            item_name = QTableWidgetItem(os.path.basename(file_path))
            self.table_widget.setItem(row_index, 0, item_name)

            # Размер
            item_size = QTableWidgetItem(f"{size_gb:.2f}")
            item_size.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table_widget.setItem(row_index, 1, item_size)

            # Vision статус
            item_vision = QTableWidgetItem("Есть" if has_vision else "")
            item_vision.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            if has_vision:
                item_vision.setForeground(green_brush)
                item_vision.setFont(bold_font)
            self.table_widget.setItem(row_index, 2, item_vision)

    def sort_by_column(self, column: int):
        if not self.models_data: 
            return
        
        # ascending - каково должно быть направление ЭТОГО клика (по умолчанию - прямой порядок)
        ascending = self._sort_states.get(column, True)
        
        if column == 0:
            self.models_data.sort(key=lambda x: os.path.basename(x[0]).lower(), reverse=not ascending)
        elif column == 1:
            self.models_data.sort(key=lambda x: x[1], reverse=not ascending)
        elif column == 2:
            self.models_data.sort(key=lambda x: x[2], reverse=not ascending)
            
        # следующий клик по этой колонке должен дать противоположный порядок
        self._sort_states[column] = not ascending
        self._populate_table(self.models_data)

    def save_sorted_list(self):
        if not self.models_data: 
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Сохранить список", "", "Текстовые файлы (*.txt)")
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as file:
                    for path, size, vision in self.models_data:
                        v_flag = "[Vision]" if vision else ""
                        file.write(f"{os.path.basename(path)}, {size:.2f} GB {v_flag}\n")
            except Exception as e:
                QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить файл: {e}")

    def on_model_double_clicked(self, item):
        row = item.row()
        if row < len(self.models_data):
            full_path, size_gb, _ = self.models_data[row]
            logging.info(f"[SW] Выбрана модель: {full_path}")
            self.model_selected.emit(full_path, size_gb)

# services/model_scanner.py
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

# config_widget.py
# -*- coding: utf-8 -*-
import os
import sys
import json
import logging
from datetime import datetime
from typing import List, Tuple, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QFileDialog, QHeaderView, QTableWidget, QTableWidgetItem, QSplitter,
    QTextEdit, QMessageBox
)
from PySide6.QtCore import Qt, Slot, Signal, QTimer

from services.model_scanner import find_files_by_extension


def _resolve_env_path() -> str:
    """.env рядом с исполняемым файлом (frozen-сборка) или со скриптом (Thonny/venv) -
    не зависит от текущей рабочей директории процесса."""
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, ".env")


# Константы для размеров сплиттеров
CONST_LAYOUT_WIDTH_TOP_LEFT = 500
CONST_LAYOUT_WIDTH_TOP_RIGHT = 400
CONST_LAYOUT_WIDTH_LEFT_VERTICAL = 300
CONST_LAYOUT_WIDTH_RIGHT_VERTICAL = 350
CONST_LAYOUT_WIDTH_RIGHT_SPLITTER = 500
CONST_LAYOUT_WIDTH_BOTTOM = 150

class ConfigWidget(QWidget):
    scan_started = Signal()
    scan_finished = Signal(list)
    run_command_requested = Signal(str)

    _LAYERS_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "model_layers.json")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_widget = parent

        self._layer_map: dict = self._load_layer_map()
        self.models_data: List[Tuple[str, float, str]] = []
        self.mods_path = None
        self.model_size = None

        # Чтение каталога модов из окружения
        self._env_path = _resolve_env_path()
        if os.path.exists(self._env_path):
            try:
                from dotenv import load_dotenv
                load_dotenv(self._env_path)
                self.mods_path = os.getenv("LAST_MODS_PATH")
            except Exception as e:
                logging.error(f"[CW] Ошибка загрузки .env: {e}")

        if not self.mods_path:
            self.mods_path = "/home/yuri/MODS/"

        logging.info(f"[CW] Итоговый путь к модам: {self.mods_path}")
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # --- ВЕРХНЯЯ ПАНЕЛЬ С ВЫРАВНИВАНИЕМ ПО ШИРИНЕ ---
        top_widget = QWidget()
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)

        # Левая часть (будет строго над левым сплиттером)
        left_top_part = QWidget()
        left_top_layout = QHBoxLayout(left_top_part)
        left_top_layout.setContentsMargins(0, 0, 10, 0)
        left_top_layout.setSpacing(6)

        model_name_label = QLabel("Модель:")
        self.model_name_edit = QLineEdit()
        self.model_name_edit.setReadOnly(True)

        self.size_label = QLabel()
        self.size_label.setStyleSheet("color: grey; font-size: 12px;")

        left_top_layout.addWidget(model_name_label)
        left_top_layout.addWidget(self.model_name_edit, 1)  # Поле ввода забирает ВСЁ доступное пространство
        left_top_layout.addWidget(self.size_label)

        # Правая часть (будет строго над правым сплиттером)
        right_top_part = QWidget()
        right_top_layout = QHBoxLayout(right_top_part)
        right_top_layout.setContentsMargins(10, 0, 0, 0)
        right_top_layout.setSpacing(0)

        self.button_modfiles = QPushButton("Обзор")
        self.button_modfiles.clicked.connect(self._browse_mods_directory)

        self.mods_path_label = QLabel(f"Каталог: {self.mods_path}")
        self.mods_path_label.setStyleSheet("color: grey; font-size: 12px;")
        self.mods_path_label.setToolTip(self.mods_path)
        self.mods_path_label.setMaximumWidth(200)

        right_top_layout.addWidget(self.mods_path_label)
        right_top_layout.addStretch()  # Прижимает кнопку к самому правому краю окна
        right_top_layout.addWidget(self.button_modfiles)

        # Собираем верхний контейнер с жесткими весами сплиттеров
        top_layout.addWidget(left_top_part, CONST_LAYOUT_WIDTH_TOP_LEFT)
        top_layout.addWidget(right_top_part, CONST_LAYOUT_WIDTH_TOP_RIGHT)
        layout.addWidget(top_widget)

        # --- ГЛАВНЫЙ СПЛИТТЕР (Дальше код остается без изменений) ---
        self.h_splitter = QSplitter(Qt.Horizontal)

        # Левый рабочий блок (Таблица + Просмотрщик)
        self.left_v_splitter = QSplitter(Qt.Vertical)

        self.output_table = QTableWidget()
        self.output_table.setColumnCount(3)
        self.output_table.setHorizontalHeaderLabels(["Имя файла .mod", "Папка", "Дата (модификации)"])
        self.output_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.output_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.output_table.setSelectionMode(QTableWidget.SingleSelection)
        self.output_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.output_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.output_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.output_table.itemDoubleClicked.connect(self.on_model_double_clicked)

        self.text_edit_left = QTextEdit()
        self.text_edit_left.setReadOnly(True)
        self.text_edit_left.setLineWrapMode(QTextEdit.NoWrap)

        self.left_v_splitter.addWidget(self.output_table)
        self.left_v_splitter.addWidget(self.text_edit_left)

        # Правый рабочий блок (Редактор + Функциональные кнопки)
        self.right_v_splitter = QSplitter(Qt.Vertical)

        self.text_edit_right = QTextEdit()
        self.text_edit_right.setLineWrapMode(QTextEdit.NoWrap)

        buttons_container = QWidget()
        buttons_layout = QVBoxLayout(buttons_container)
        buttons_layout.setContentsMargins(0, 5, 0, 0)
        buttons_layout.setSpacing(6)

        self.button_clear = QPushButton("Сбросить")
        self.button_get = QPushButton("Загрузить")
        self.button_save = QPushButton("Сохранить")
        self.button_manage = QPushButton("Сервер")

        self.button_clear.clicked.connect(self.on_clear_clicked)
        self.button_get.clicked.connect(self.on_get_clicked)
        self.button_save.clicked.connect(self.on_save_config_clicked)
        self.button_manage.clicked.connect(self.on_manage_clicked)

        buttons_layout.addWidget(self.button_clear)
        buttons_layout.addWidget(self.button_get)
        buttons_layout.addWidget(self.button_save)
        buttons_layout.addWidget(self.button_manage)

        self.right_v_splitter.addWidget(self.text_edit_right)
        self.right_v_splitter.addWidget(buttons_container)

        # Сборка геометрии
        self.h_splitter.addWidget(self.left_v_splitter)
        self.h_splitter.addWidget(self.right_v_splitter)
        layout.addWidget(self.h_splitter, 1)

        # Точные пропорции окон из ТЗ
        self.h_splitter.setSizes([CONST_LAYOUT_WIDTH_TOP_LEFT, CONST_LAYOUT_WIDTH_TOP_RIGHT])
        self.left_v_splitter.setSizes([CONST_LAYOUT_WIDTH_LEFT_VERTICAL, CONST_LAYOUT_WIDTH_RIGHT_VERTICAL])
        self.right_v_splitter.setSizes([CONST_LAYOUT_WIDTH_RIGHT_SPLITTER, CONST_LAYOUT_WIDTH_BOTTOM])

        self.model_name_edit.setPlaceholderText("Имя выбранной .gguf модели")
        self.text_edit_left.setPlaceholderText("Содержимое .mod (только чтение)")
        self.text_edit_right.setPlaceholderText("Редактируемое содержимое")

    def _browse_mods_directory(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Выбрать каталог с .mod файлами", self.mods_path or ""
        )
        if not directory:
            return

        self.mods_path = directory
        # Обновляем отображение пути
        self.mods_path_label.setText(f"Каталог: {self.mods_path}")
        try:
            from dotenv import set_key
            set_key(self._env_path, "LAST_MODS_PATH", self.mods_path)
            logging.info(f"[CW] Каталог модов сохранён в .env: {self.mods_path}")
        except Exception as e:
            logging.error(f"[CW] Не удалось сохранить LAST_MODS_PATH в .env: {e}")
            QMessageBox.warning(self, "Предупреждение",
                                 f"Каталог выбран, но не сохранён в .env:\n{e}")

        self.start_scan()

    def showEvent(self, event):
        super().showEvent(event)
        # Подстраховка от устаревшего списка .mod: пересканируем при каждом
        # реальном показе вкладки, а не только один раз при старте приложения.
        self.start_scan()

    def _load_layer_map(self) -> dict:
        try:
            with open(self._LAYERS_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logging.warning(f"[CW] Не удалось загрузить model_layers.json: {e}. Используется дефолт.")
            return {"7B": 32, "8B": 32, "12B": 40, "13B": 40, "70B": 80}

    def _resolve_n_layer(self, model_name: str) -> int:
        upper = model_name.upper()
        # Сначала проверяем точное совпадение
        if upper in self._layer_map:
            return self._layer_map[upper]
        # Затем ищем по префиксу, сортируя по длине обратно
        for size_str, layers in sorted(self._layer_map.items(), key=lambda x: -len(x[0])):
            if upper.startswith(size_str.upper()):
                return layers
        return 32

    # ---------------------------------------------------------
    #  Установка выбранной модели из главного интерфейса
    # ---------------------------------------------------------
    @Slot(str, float)
    def set_model(self, full_path: str, model_size_gb: float):
        model_name = os.path.basename(full_path)
        logging.info(f"[CW] Синхронизация модели: {model_name} ({model_size_gb} GB)")

        if not model_name:
            self.model_name_edit.clear()
            self.size_label.clear()
            self.text_edit_left.clear()
            self.text_edit_right.clear()
            self._current_mod_file_path = None
            self.model_size = None
            self._populate_table([])
            return

        self.model_name_edit.setText(model_name)
        self.model_size = model_size_gb * 1024  # Конвертируем в МБ
        self.size_label.setText(f"{model_size_gb:.3f} ГБ")

        base = model_name.rsplit(".", 1)[0]
        mods = self._find_mods_for_base(base)

        if mods:
            self._populate_table(mods)
            self.text_edit_left.clear()
            self.text_edit_right.clear()
            self._current_mod_file_path = None
            self.button_get.setText("Загрузить")
            self.button_get.setEnabled(False)
        else:
            # Если файла настроек нет — генерируем полный шаблон
            self._populate_table([])
            self.text_edit_right.clear()
            self._current_mod_file_path = None

            content = self._generate_auto_config(model_name, self.model_size)
            self.text_edit_left.setPlainText(content)

            self.button_get.setText("Загрузить")
            self.button_get.setEnabled(True)

    # ---------------------------------------------------------
    #  Исправленный генератор параметров (С сохранением структуры каталогов)
    # ---------------------------------------------------------
    def _generate_auto_config(self, model_name: str, size_mb: float) -> str:
        quant = self._detect_quant(model_name)
        gpu_ram = int(os.getenv("GPU_RAM_GB", "12"))
        ctx, ngl_raw, threads, batch_raw = self._select_params(quant, gpu_ram)

        size_gb = size_mb / 1024

        ctx_final = ctx
        batch_final = batch_raw

        if size_gb > 10:
            ctx_final = 16384
            batch_final = 96
        if size_gb > 13:
            ctx_final = 12288
            batch_final = 64
        if size_gb > 18:
            ctx_final = 8192

        n_layer = self._resolve_n_layer(model_name)
        ngl_final = min(ngl_raw, n_layer)

        extra_param = '--flash-attn' if ctx_final > 32768 else ''

        # ДИНАМИЧЕСКИЙ ПУТЬ:
        # Если имя модели (без расширения) совпадает с концептом папки или это тяжелая модель,
        # собираем путь вида: /srv/models/Имя_Модели_Без_Расширения/Имя_Модели.gguf
        base_folder = model_name.rsplit(".", 1)[0]

        # Общий механизм — каждая модель в своей папке
        srv_path = f'/srv/models/{base_folder}/{model_name}'

        # Собираем чистый монолитный текст
        lines = [
            f'MODEL="{srv_path}"',
            'HOST="0.0.0.0"',
            'PORT="8080"',
            '',
            f'THREADS="{threads}"',
            '',
            f'CTX="{ctx_final}"',
            f'BATCH="{batch_final}"',
            f'NGL="{ngl_final}"',
            '',
            f'EXTRA="{extra_param}"'
        ]
        return "\n".join(lines) + "\n"

    def _perform_autopick(self):
        model_name = self.model_name_edit.text().strip()
        if not model_name or self.model_size is None:
            return
        content = self._generate_auto_config(model_name, self.model_size)
        self.text_edit_right.setPlainText(content)
        self.text_edit_left.clear()

    def _is_hidden_path(self, path: str, base: str) -> bool:
        """True, если файл лежит в подпапке (на любом уровне вложенности),
        имя которой начинается с '_'. Имя самого файла не учитывается."""
        rel_parts = os.path.relpath(path, base).split(os.sep)
        return any(part.startswith("_") for part in rel_parts[:-1])

    def _find_mods_for_base(self, base_name: str) -> list:
        # models_data — список 4-кортежей (path, size_mb, date_str, folder_name)
        return [m for m in self.models_data if os.path.basename(m[0]).startswith(base_name)]

    def _detect_quant(self, model_name: str) -> str:
        name_upper = model_name.upper()
        for q in ["Q8_0", "Q6_K_L", "Q6_K", "Q5_K_M", "Q5_K_S", "Q4_K_M", "Q4_K_S", "Q4_0", "Q3_K", "Q2_K", "FP8", "F16", "FP16"]:
            if q in name_upper:
                return q
        return "Q4_K_M"

    def _select_params(self, quant: str, gpu_ram_gb: int):
        threads = 4
        ctx = 32768 if gpu_ram_gb <= 12 else (40960 if gpu_ram_gb <= 16 else 65536)
        v = 12 if gpu_ram_gb <= 12 else (16 if gpu_ram_gb <= 16 else 24)

        ngl_table = {
            "Q2_K":   {12: 80, 16: 100, 24: 120},
            "Q3_K":   {12: 72, 16: 90,  24: 110},
            "Q4_K_M": {12: 60, 16: 72,  24: 96},
            "Q5_K_M": {12: 52, 16: 64,  24: 84},
            "Q6_K_L": {12: 48, 16: 60,  24: 80},
            "Q8_0":   {12: 40, 16: 52,  24: 72},
        }
        ngl = ngl_table.get(quant, {12: 32}).get(v, 32)

        batch_table = {
            "Q2_K": 512, "Q3_K": 384, "Q4_K_M": 320, "Q5_K_M": 192, "Q6_K_L": 256, "Q8_0": 192,
        }
        batch = batch_table.get(quant, 128)
        return ctx, ngl, threads, batch

    def start_scan(self):
        if not self.mods_path or not os.path.isdir(self.mods_path):
            return
        self.scan_started.emit()
        try:
            raw_mod_files = find_files_by_extension(self.mods_path, ".mod")
            models_processed = []
            for file_path, size_bytes, timestamp in raw_mod_files:
                # Пропускаем пресеты, лежащие в подпапках с префиксом '_'
                if self._is_hidden_path(file_path, self.mods_path):
                    continue
                size_mb = size_bytes / (1024 ** 2)
                date_str = datetime.fromtimestamp(timestamp).strftime("%Y.%m.%d %H:%M")
                # Имя родительской папки (пусто, если файл лежит в корне MODS)
                rel_parts = os.path.relpath(file_path, self.mods_path).split(os.sep)
                folder_name = rel_parts[-2] if len(rel_parts) > 1 else ""
                models_processed.append((file_path, size_mb, date_str, folder_name))

            self.models_data = models_processed

            current_model = self.model_name_edit.text().strip()
            if current_model:
                base = current_model.rsplit(".", 1)[0]
                self._populate_table(self._find_mods_for_base(base))
            else:
                self._populate_table(self.models_data)
        except FileNotFoundError:
            logging.error(f"[CW] Папка с модами не найдена: {self.mods_path}")
        except Exception as e:
            logging.error(f"[CW] Ошибка сканирования: {e}")
        finally:
            self.button_modfiles.setEnabled(True)

    def _populate_table(self, models: List[Tuple[str, float, str, str]]):
        models_sorted = sorted(models, key=lambda x: os.path.basename(x[0]))
        self.output_table.setRowCount(len(models_sorted))

        for row_index, (file_path, _, date_str, folder_name) in enumerate(models_sorted):
            item_name = QTableWidgetItem(os.path.basename(file_path))
            item_name.setData(Qt.UserRole, file_path)

            item_folder = QTableWidgetItem(folder_name or "—")
            item_folder.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

            item_date = QTableWidgetItem(date_str)
            item_date.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            self.output_table.setItem(row_index, 0, item_name)
            self.output_table.setItem(row_index, 1, item_folder)
            self.output_table.setItem(row_index, 2, item_date)

    def on_model_double_clicked(self, item):
        row = item.row()
        path_item = self.output_table.item(row, 0)
        if not path_item:
            return
        mod_path = path_item.data(Qt.UserRole)
        if not mod_path or not os.path.exists(mod_path):
            return
        try:
            with open(mod_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.text_edit_left.setPlainText(content)
            self._current_mod_file_path = mod_path
            self.button_get.setText("Загрузить")
            self.button_get.setEnabled(True)
        except Exception as e:
            self.text_edit_left.setPlainText(str(e))

    def on_get_clicked(self):
        mode = self.button_get.text()
        if mode == "Загрузить":
            self.text_edit_right.setPlainText(self.text_edit_left.toPlainText())
        elif mode == "Автоподбор":
            self._perform_autopick()

    def on_clear_clicked(self):
        self.text_edit_left.clear()
        self.text_edit_right.clear()
        self._current_mod_file_path = None
        self.button_get.setText("Загрузить")
        self.button_get.setEnabled(False)

    def on_save_config_clicked(self):
        content_to_save = self.text_edit_right.toPlainText().strip()
        if not content_to_save:
            QMessageBox.warning(self, "Ошибка", "Нет данных для сохранения.")
            return

        default_name = "config"
        if self._current_mod_file_path:
            default_name = os.path.splitext(os.path.basename(self._current_mod_file_path))[0]
        else:
            model_name = self.model_name_edit.text().strip()
            if model_name:
                default_name = os.path.splitext(model_name)[0]

        if not self.mods_path:
            QMessageBox.warning(self, "Ошибка", "Не выбран каталог с модами.")
            return
        initial_path = os.path.join(self.mods_path, f"{default_name}.mod")
        file_path, accepted = QFileDialog.getSaveFileName(
            self, "Сохранить конфигурацию (.mod)", initial_path, "MOD Files (*.mod);;All Files (*)"
        )
        if not accepted:
            return
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content_to_save)
            QMessageBox.information(self, "Успех", "Файл успешно сохранён.")
            self.start_scan()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка сохранения", str(e))

    def on_manage_clicked(self):
        command_string = self.text_edit_right.toPlainText().strip()
        if command_string:
            self.run_command_requested.emit(command_string)

# server_widget.py
# -*- coding: utf-8 -*-
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QRadioButton,
    QButtonGroup, QLabel,
    QMessageBox, QTextEdit, QSplitter
)
from PySide6.QtCore import Qt, QProcess, QProcessEnvironment
from PySide6.QtGui import QFont
import os
import sys
import logging
from dotenv import load_dotenv

from services.ssh_setup import SSHSetupHelper
from services.ssh_manager import SSHManager


def _resolve_env_path() -> str:
    """.env рядом с исполняемым файлом (frozen-сборка) или со скриптом (Thonny/venv)."""
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, ".env")


# Загружаем конфигурацию из .env
_env_path = _resolve_env_path()
if os.path.exists(_env_path):
    load_dotenv(_env_path)
else:
    load_dotenv()  # fallback

SPLITTER_SIZES = [420, 240]
SSH_HOST = os.getenv("SSH_HOST", "rtx")

# Проверка наличия SSH-ключа при импорте модуля — для информативного лога.
# Сам ключ используется лениво, через SSHManager.get_ssh_key_path(),
# чтобы избежать повторных os.path.exists при каждом клике.
if not SSHManager.get_ssh_key_path():
    logging.warning(
        "[ServerWidget] SSH-ключ не найден. Беспарольный доступ не работает. "
        "Выполните: ssh-keygen -t ed25519 && ssh-copy-id yuri@rtx"
    )

# Два управляемых инстанса. "" - пустой суффикс llmctl-команды: сохраняет
# полную обратную совместимость с автостартующим llama-server.service
# (никаких изменений в systemd/llmctl для порта 8080 не требуется).
INSTANCES = {
    "8080": {
        "label": "Модель 1 (порт 8080, автостарт)",
        "config_path": os.getenv("DEFAULT_CONFIG_PATH", "/media/rtx-storage/llama-mode.conf"),
        "llmctl_suffix": "",
    },
    "8081": {
        "label": "Модель 2 (порт 8081, вручную, GPU1)",
        "config_path": os.getenv("SECOND_CONFIG_PATH", "/media/rtx-storage/llama-mode-8081.conf"),
        "llmctl_suffix": " 8081",
    },
}


class ServerControlWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_stream_process = None
        self.monitor_thread = None  # Ссылка на поток мониторинга
        self.current_instance = "8080"  # инстанс по умолчанию - основной, автостартующий

        # Главный вертикальный макет
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Переключатель инстанса - к какой модели относятся кнопки ниже
        instance_layout = QHBoxLayout()
        instance_layout.addWidget(QLabel("Управляем:"))
        self.instance_group = QButtonGroup(self)
        for key, info in INSTANCES.items():
            rb = QRadioButton(info["label"])
            rb.setChecked(key == self.current_instance)
            rb.toggled.connect(lambda checked, k=key: self._on_instance_changed(k, checked))
            self.instance_group.addButton(rb)
            instance_layout.addWidget(rb)
        instance_layout.addStretch()
        main_layout.addLayout(instance_layout)

        # Сплиттер для разделения логов и зоны управления
        self.splitter = QSplitter(Qt.Vertical, self)

        # Верхнее текстовое поле (Логи / Статус)
        self.server_log_text_edit = QTextEdit()
        self.server_log_text_edit.setReadOnly(True)
        self.server_log_text_edit.setFont(QFont("DejaVu Sans Mono", 10))
        self.server_log_text_edit.setPlaceholderText("Здесь будут отображаться логи, статус или конфигурация сервера...")

        # Нижний виджет-контейнер, объединяющий поле ввода и цветные кнопки
        bottom_container = QWidget()
        bottom_layout = QHBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(10)

        # Поле конфигурации
        self.command_text_edit = QTextEdit()
        self.command_text_edit.setFont(QFont("DejaVu Sans Mono", 10))
        self.command_text_edit.setPlaceholderText("Вставьте конфигурацию. Строки, начинающиеся с INFO:, будут сохранены только локально.")

        # Вертикальный блок для цветных кнопок питания (справа от поля ввода)
        power_buttons_layout = QVBoxLayout()
        power_buttons_layout.setContentsMargins(0, 0, 0, 0)
        power_buttons_layout.setSpacing(8)
        self.btn_wol = QPushButton("Включить (WoL)")
        self.btn_wol.setStyleSheet("background-color: #1e7e34; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_wol.setFixedSize(130, 36)  # Компактный фиксированный размер
        self.btn_shutdown = QPushButton("Выключить (SSH)")
        self.btn_shutdown.setStyleSheet("background-color: #bd2130; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_shutdown.setFixedSize(130, 36)
        power_buttons_layout.addWidget(self.btn_wol)
        power_buttons_layout.addWidget(self.btn_shutdown)
        power_buttons_layout.addStretch()  # Прижимаем кнопки к верхнему краю зоны

        bottom_layout.addWidget(self.command_text_edit, stretch=1)
        bottom_layout.addLayout(power_buttons_layout)

        # Добавляем элементы в сплиттер
        self.splitter.addWidget(self.server_log_text_edit)
        self.splitter.addWidget(bottom_container)
        self.splitter.setSizes(SPLITTER_SIZES)
        main_layout.addWidget(self.splitter, stretch=1)

        # Нижняя панель управления (Кнопки идут строго вровень с нижней границей окна)
        self.control_button_layout = QHBoxLayout()
        self.control_button_layout.setContentsMargins(0, 2, 0, 2)
        self.control_button_layout.setSpacing(6)
        button_specs = [
            ("apply", "Применить", self.set_config_file),
            ("start", "Старт", self.start_llama_server),
            ("stop", "Стоп", self.stop_llama_server),
            ("restart", "Перезапуск", self.restart_llama_server),
            ("status", "Статус", self.show_server_status),
            ("config", "Конфиг", self.show_llama_mode_conf),
            ("logs", "Логи", self.show_server_logs)
        ]
        for key, text, handler in button_specs:
            btn = QPushButton(text)
            btn.clicked.connect(handler)
            btn.setFixedHeight(30)  # Исправлено с setHeight
            self.control_button_layout.addWidget(btn)
        main_layout.addLayout(self.control_button_layout)

    def set_monitor_thread(self, monitor_thread):
        """Метод вызывается из main_ui для передачи потока мониторинга."""
        self.monitor_thread = monitor_thread
        # Привязываем действия к кнопкам питания через объект потока
        self.btn_wol.clicked.connect(lambda: self._trigger_power_action(self.monitor_thread.send_wake_on_lan, "WoL"))
        self.btn_shutdown.clicked.connect(lambda: self._trigger_power_action(self.monitor_thread.shutdown_host, "Выключение"))
        # Подключаем сигналы изменения статуса из потока для вывода в текстовое поле
        self.monitor_thread.shutdown_status_received.connect(self._append_system_msg)
        self.monitor_thread.wol_status_received.connect(self._append_system_msg)

    def _append_system_msg(self, msg: str):
        """Вывод системных уведомлений о питании в лог-панель"""
        self.server_log_text_edit.append(f"[Питание]: {msg}")
        self.server_log_text_edit.ensureCursorVisible()

    def _trigger_power_action(self, method, name):
        self.server_log_text_edit.append(f"[Питание]: Выполнение команды {name}...")
        method()

    def update_command_display(self, command_string):
        self.command_text_edit.setPlainText(command_string)

    def _on_instance_changed(self, key, checked):
        if checked:
            self.current_instance = key
            self.server_log_text_edit.append(f"[Система]: Переключено на {INSTANCES[key]['label']}")

    def stop_current_stream(self):
        if self.current_stream_process and self.current_stream_process.state() == QProcess.Running:
            self.current_stream_process.terminate()
            self.current_stream_process = None

    def run_async_ssh_cmd(self, action_arg, clear_output=True, is_stream=False):
        """Запуск команд через SSH-ключи и sudo NOPASSWD.
        Требует настроенного беспарольного доступа на сервере.
        action_arg относится к текущему выбранному через радио-кнопки инстансу."""
        # Проверка SSH-ключа перед выполнением — через единый менеджер
        if not SSHManager.get_ssh_key_path():
            reply = QMessageBox.question(
                self, "SSH-ключ не найден",
                "Беспарольный доступ не настроен. Команда не может быть выполнена.\n\n"
                "Хотите открыть мастер настройки?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._show_ssh_setup_wizard()
            return

        self.stop_current_stream()
        suffix = INSTANCES[self.current_instance]["llmctl_suffix"]
        full_action = f"{action_arg}{suffix}"
        if clear_output:
            self.server_log_text_edit.clear()
        self.server_log_text_edit.append(f"[Система]: Отправка команды 'llmctl {full_action}' на {SSH_HOST}...\n")

        proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        proc.setProcessEnvironment(env)

        def read_stdout():
            data = proc.readAllStandardOutput().data().decode('utf-8', errors='ignore')
            if data:
                self.server_log_text_edit.insertPlainText(data)
                self.server_log_text_edit.ensureCursorVisible()

        def read_stderr():
            data = proc.readAllStandardError().data().decode('utf-8', errors='ignore')
            if not data:
                return
            # Игнорируем технические предупреждения SSH о псевдо-терминалах, если они проскочат
            if "Pseudo-terminal" in data:
                return
            lower_data = data.lower()
            # Мониторинг фатальных ошибок инференса и железа
            fatal_keywords = ["out of memory", "cuda error", "kv cache full", "failed to allocate", "assert"]
            if any(keyword in lower_data for keyword in fatal_keywords):
                self.server_log_text_edit.insertPlainText(f"\n[КРИТИЧЕСКАЯ ОШИБКА]: {data}\n")
            else:
                self.server_log_text_edit.insertPlainText(f"\n[Инфо]: {data}")
            self.server_log_text_edit.ensureCursorVisible()

        proc.readyReadStandardOutput.connect(read_stdout)
        proc.readyReadStandardError.connect(read_stderr)

        # Формируем аргументы SSH через единый менеджер
        ssh_args = SSHManager.get_ssh_base_args(
            SSH_HOST,
            f"sudo /usr/local/bin/llmctl {full_action}"
        )
        if not ssh_args:
            # Менеджер не нашёл ключ — это уже обработано выше, но на всякий случай
            self.server_log_text_edit.append("[Ошибка]: SSH-ключ не найден, команда отменена.")
            return

        proc.start("ssh", ssh_args)
        if proc.state() == QProcess.NotRunning:
            self.server_log_text_edit.append(f"[Ошибка]: Не удалось запустить SSH-соединение")
            return

        if is_stream:
            self.current_stream_process = proc

    def _show_ssh_setup_wizard(self):
        """Открывает диалог настройки беспарольного SSH-доступа к серверу.
        Все действия выполняются прямо из диалога (по нажатию кнопки),
        поэтому достаточно одного exec() — после каждого действия статус
        показывается в том же окне, а не в новом.
        """
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Настройка SSH-доступа")
        dialog.setText("Беспарольный SSH-доступ не настроен.")
        dialog.setInformativeText(
            "Для работы приложения необходим беспарольный доступ к серверу.\n\n"
            "Что вы хотите сделать?"
        )
        btn_gen = dialog.addButton("Сгенерировать ключ", QMessageBox.AcceptRole)
        btn_copy = dialog.addButton("Скопировать ключ на сервер", QMessageBox.AcceptRole)
        btn_inst = dialog.addButton("Показать инструкцию sudoers", QMessageBox.AcceptRole)
        dialog.addButton(QMessageBox.Close)
        dialog.exec()

        if dialog.clickedButton() == btn_gen:
            result = SSHSetupHelper.generate_ssh_key()
            # После генерации сбрасываем кэш менеджера, чтобы он увидел новый файл
            SSHManager.reset_cache()
        elif dialog.clickedButton() == btn_copy:
            result = SSHSetupHelper.copy_key_to_host(
                os.getenv("SERVER_USER", "yuri"),
                os.getenv("SSH_HOST", "rtx")
            )
        elif dialog.clickedButton() == btn_inst:
            instructions = SSHSetupHelper.get_sudoers_instructions()
            dialog.setDetailedText(instructions)
            dialog.exec()
            return
        else:
            return  # Отмена/закрытие — ничего не делаем

        dialog.setInformativeText(result)
        dialog.exec()

    def confirm_action(self, action_title, message):
        reply = QMessageBox.question(
            self, action_title, message,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        return reply == QMessageBox.Yes

    def _validate_config(self, content: str) -> list:
        """Проверки на конкретные способы сломать конфиг, с которыми уже сталкивались:
        конфликт NGL=auto + ручной --tensor-split (реальный OOM), пропущенные пробелы
        перед \\ в многострочном EXTRA (слипшиеся аргументы), отсутствие обязательных
        ключей, невалидные диапазоны PORT/CTX/NGL."""
        issues = []
        lines = content.splitlines()
        required_keys = ["MODEL", "PORT", "CTX", "NGL"]
        found_keys = set()
        ngl_value = None
        port_value = None
        ctx_value = None
        has_manual_tensor_split = "--tensor-split" in content
        for i, raw_line in enumerate(lines, 1):
            line = raw_line.strip()
            if not line:
                continue
            # KEY="VALUE" в начале строки
            if "=" in line:
                key = line.split("=", 1)[0].strip()
                if key.isidentifier():
                    found_keys.add(key)
                    if key == "NGL":
                        ngl_value = line.split("=", 1)[1].strip().strip('"')
                    elif key == "PORT":
                        port_value = line.split("=", 1)[1].strip().strip('"')
                    elif key == "CTX":
                        ctx_value = line.split("=", 1)[1].strip().strip('"')
            # Многострочное значение (EXTRA="...\): пробел обязателен перед \
            if raw_line.rstrip().endswith("\\"):
                before_backslash = raw_line.rstrip()[:-1]
                if before_backslash and not before_backslash.endswith(" "):
                    issues.append(
                        f"Строка {i}: нет пробела перед '\\' — следующая строка слипнется "
                        f"с этой в один аргумент (...\"{before_backslash[-20:]}\\\")."
                    )
        # Проверка обязательных ключей
        missing = [k for k in required_keys if k not in found_keys]
        if missing:
            issues.append(f"Отсутствуют обязательные параметры: {', '.join(missing)}")
        # Проверка PORT
        if port_value:
            try:
                port = int(port_value)
                if not (1 <= port <= 65535):
                    issues.append(f"PORT: невалидный диапазон (1-65535)")
            except ValueError:
                issues.append(f"PORT: должно быть числом")
        # Проверка CTX
        if ctx_value:
            try:
                ctx = int(ctx_value)
                if ctx < 8:
                    issues.append(f"CTX: слишком маленький (минимум 8)")
            except ValueError:
                issues.append(f"CTX: должно быть числом")
        # Проверка NGL
        if ngl_value and ngl_value != "auto":
            try:
                ngl = int(ngl_value)
                if ngl <= 0:
                    issues.append(f"NGL: должно быть > 0")
            except ValueError:
                issues.append(f"NGL: должно быть числом или 'auto'")
        if ngl_value == "auto" and has_manual_tensor_split:
            issues.append(
                "NGL=\"auto\" вместе с ручным --tensor-split — именно эта комбинация "
                "уже роняла запуск с OOM (auto-fit прерывается при заданном tensor-split). "
                "Либо уберите --tensor-split, либо задайте NGL числом."
            )
        return issues

    def set_config_file(self):
        raw_content = self.command_text_edit.toPlainText()
        if not raw_content.strip():
            QMessageBox.warning(self, "Внимание", "Конфигурация пуста. Нечего сохранять.")
            return
        issues = self._validate_config(raw_content)
        if issues:
            details = "\n".join(f"• {i}" for i in issues)
            reply = QMessageBox.warning(
                self, "Найдены потенциальные проблемы",
                f"{details}\n\nВсё равно сохранить как есть?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
        filtered_lines = []
        info_count = 0
        for line in raw_content.splitlines():
            if line.strip().upper().startswith("INFO:"):
                info_count += 1
                continue
            filtered_lines.append(line)
        filtered_content = "\n".join(filtered_lines)
        target_path = INSTANCES[self.current_instance]["config_path"]
        try:
            with open(target_path, 'w') as file:
                file.write(filtered_content)
            self.server_log_text_edit.clear()
            msg = f"[Система]: Конфигурация сохранена в {target_path} ({INSTANCES[self.current_instance]['label']})\n"
            if info_count > 0:
                msg += f"[Система]: Из файла конфигурации локально исключено {info_count} строк(и) заметок INFO:\n"
            msg += "Изменения вступят в силу после Старта или Перезапуска сервера."
            self.server_log_text_edit.setText(msg)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось записать файл: {str(e)}")

    def _instance_label(self):
        return INSTANCES[self.current_instance]["label"]

    def start_llama_server(self):
        if self.confirm_action("Запуск сервера", f"Запустить {self._instance_label()}?"):
            self.run_async_ssh_cmd("start")

    def stop_llama_server(self):
        if self.confirm_action("Остановка сервера", f"Остановить {self._instance_label()}?"):
            self.run_async_ssh_cmd("stop")

    def restart_llama_server(self):
        if self.confirm_action("Перезапуск сервера", f"Перезапустить {self._instance_label()}?"):
            self.run_async_ssh_cmd("restart")

    def show_server_status(self):
        self.run_async_ssh_cmd("status")

    def show_llama_mode_conf(self):
        self.run_async_ssh_cmd("mode")

    def show_server_logs(self):
        self.run_async_ssh_cmd("logs", is_stream=True)

    def closeEvent(self, event):
        self.stop_current_stream()
        event.accept()

# services/ssh_setup.py
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

