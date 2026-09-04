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

from locale_manager import locale

# Язык интерфейса берём из .env (LANGUAGE=ru/en/es); по умолчанию — английский
locale.load_locale(os.getenv("LANGUAGE"))

from services.system_monitor import RemoteMonitorThread
from services.server_control import ServerControl
from scanner_widget import ScannerWidget
from config_widget import ConfigWidget
from server_widget import ServerControlWidget

class MainWindow(QMainWindow):
    system_usage_updated = Signal(dict)   # Сигнал без жестких типов данных

    def __init__(self) -> None:
        super().__init__()

        # Последние полученные метрики (для повторного применения при смене языка)
        self._last_stats: Optional[Dict[str, Any]] = None

        # 1. Инициализируем фоновые сервисы и запускаем поток мониторинга (один раз)
        self.system_monitor: Optional[RemoteMonitorThread] = RemoteMonitorThread()
        self.system_monitor.start()
        self.server_control: ServerControl = ServerControl()

        # Настройки главного окна. Ширину берём из .env (APP_WIDTH),
        # по умолчанию — 1380; высоту оставляем 720.
        self.setWindowTitle("LLM-Control BY")
        try:
            window_width = int(os.getenv("APP_WIDTH", "1380"))
        except ValueError:
            window_width = 1380
        self.setGeometry(100, 100, window_width, 720)

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
        self.tab_widget.addTab(self.scanner_tab, locale.translate('tab.models'))

        # Таб 2: Параметры модели
        self.config_tab = QWidget()
        self.config_tab_layout = QVBoxLayout(self.config_tab)
        self.config_widget = ConfigWidget(self)
        self.config_tab_layout.addWidget(self.config_widget)
        self.tab_widget.addTab(self.config_tab, locale.translate('tab.params'))

        # Таб 3: Управление сервером
        self.control_tab = QWidget()
        self.control_tab_layout = QVBoxLayout(self.control_tab)
        
        # Важно: создаем ServerControlWidget
        self.control_widget = ServerControlWidget(self)
        self.control_tab_layout.addWidget(self.control_widget)
        self.tab_widget.addTab(self.control_tab, locale.translate('tab.server'))

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

        self._set_placeholder_status()
        self._init_metrics_labels()
        self._connect_signals()
        # По умолчанию открываем вкладку «Параметры модели» — там работа с пресетами
        self.tab_widget.setCurrentIndex(0)

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

        # Смена языка в ConfigWidget → перекладываем весь интерфейс
        self.scanner_widget.language_changed.connect(self.retranslate_ui)

    def _on_command_requested(self, command_string: str) -> None:
        """Обработка конфигурационной команды, полученной из ConfigWidget."""
        logging.info(f"[MAIN_UI] Получена команда от ConfigWidget: {command_string}")
        self.tab_widget.setCurrentWidget(self.control_tab)
        self.control_widget.update_command_display(command_string)

    def _save_settings(self) -> None:
        try:
            last_scan_path = self.scanner_widget.current_scan_path
            last_save_path = self.scanner_widget.current_save_path
            last_model_path = getattr(self.scanner_widget, "last_selected_path", "")
            set_key(".env", "LAST_SCAN_PATH", last_scan_path)
            set_key(".env", "LAST_SAVE_PATH", last_save_path)
            set_key(".env", "LAST_MODEL_PATH", last_model_path)
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
        self._last_stats = stats
        self._apply_status_labels(stats)

    def _set_placeholder_status(self) -> None:
        """Заполняем статус-бар текстами-заполнителями по текущему языку."""
        self.cpu_label.setText(f"{locale.translate('status.cpu')} --")
        self.ram_label.setText(f"{locale.translate('status.ram')} --")
        self.llama_label.setText(f"{locale.translate('status.llama')} --")
        self.llama2_label.setText(f"{locale.translate('status.llama2')} --")
        self.gpu_label.setText(f"{locale.translate('status.gpu')} --")

    def _apply_status_labels(self, stats: Dict[str, Any]) -> None:
        """Применяет метрики к статус-бару, локализуя только префиксы (данные — нет)."""
        try:
            system = stats["system"]
            instances = stats.get("instances", {})
            gpus = stats.get("gpu", [])

            self.cpu_label.setText(f"{locale.translate('status.cpu')} {system['cpu']:.1f}%")
            self.ram_label.setText(f"{locale.translate('status.ram')} {system['ram']:.1f}%")

            inst_8080 = instances.get(8080, {})
            if inst_8080.get("running"):
                self.llama_label.setText(f"{locale.translate('status.llama')}ACTIVE | {inst_8080.get('vram_gb', 0.0):.2f} GB")
            else:
                self.llama_label.setText(f"{locale.translate('status.llama')}OFFLINE")

            inst_8081 = instances.get(8081, {})
            if inst_8081.get("running"):
                self.llama2_label.setText(f"{locale.translate('status.llama2')}ACTIVE | {inst_8081.get('vram_gb', 0.0):.2f} GB")
            else:
                self.llama2_label.setText(f"{locale.translate('status.llama2')}OFFLINE")

            if gpus:
                parts = [f"GPU{g['index']}: {g['used_gb']:.1f}/{g['total_gb']:.1f}GB {g['power_w']}W" for g in gpus]
                self.gpu_label.setText(" | ".join(parts))
            else:
                self.gpu_label.setText(f"{locale.translate('status.gpu')} --")
        except Exception as e:
            logging.error(f"[MAIN_UI] Ошибка отображения метрик: {e}")

    def retranslate_ui(self) -> None:
        """Перекладываем интерфейс при смене языка без пересоздания виджетов."""
        self.tab_widget.setTabText(0, locale.translate('tab.models'))
        self.tab_widget.setTabText(1, locale.translate('tab.params'))
        self.tab_widget.setTabText(2, locale.translate('tab.server'))

        # Перекладываем статус-бар: сначала заполнитель, затем последние метрики (если есть)
        self._set_placeholder_status()
        if self._last_stats:
            self._apply_status_labels(self._last_stats)

        # Перекладываем вложенные виджеты
        self.scanner_widget.retranslate()
        self.config_widget.retranslate()
        self.control_widget.retranslate()

    def _on_model_selected(self, full_path: str, size_gb: float) -> None:
        logging.info(f"[MAIN_UI] Выбрана модель: {os.path.basename(full_path)}")
        self.tab_widget.setCurrentWidget(self.config_tab)
        self.config_widget.set_model(full_path, size_gb)