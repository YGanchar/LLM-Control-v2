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