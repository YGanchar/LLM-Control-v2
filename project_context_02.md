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

### Файл: `main_ui.py`

```py
# main_ui.py

import logging
import os
import sys
from typing import List, Any, Dict, Optional

from dotenv import set_key, load_dotenv
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QMessageBox, QTabWidget
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
from services.ssh_setup import SSHSetupHelper
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
        self._check_ssh_prerequisites()

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

    def _check_ssh_prerequisites(self):
        """Проверяет готовность SSH-доступа при запуске."""
        # 1. Проверяем наличие SSH-ключа
        key_path = os.path.expanduser("~/.ssh/id_ed25519_llm")
        if not os.path.exists(key_path):
            # Пробуем стандартные ключи
            for kp in ["~/.ssh/id_ed25519", "~/.ssh/id_rsa"]:
                if os.path.exists(os.path.expanduser(kp)):
                    key_path = os.path.expanduser(kp)
                    break
            else:
                key_path = None
        
        if not key_path:
            self._show_ssh_setup_dialog()
            return
        
        # 2. Тестируем подключение
        success, msg = SSHSetupHelper.test_ssh_connection(
            os.getenv("SERVER_USER", "yuri"),
            os.getenv("SSH_HOST", "rtx")
        )
        
        if not success:
            self._show_ssh_setup_dialog()

    def _show_ssh_setup_dialog(self):
        """Показывает диалог настройки SSH."""
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Настройка SSH-доступа")
        dialog.setText("Беспарольный SSH-доступ не настроен.")
        dialog.setInformativeText(
            "Для работы приложения необходим беспарольный доступ к серверу.\n\n"
            "Что вы хотите сделать?"
        )
        
        # Кнопка: Сгенерировать ключ
        btn_gen = dialog.addButton("Сгенерировать ключ", QMessageBox.AcceptRole)
        # Кнопка: Скопировать ключ
        btn_copy = dialog.addButton("Скопировать ключ на сервер", QMessageBox.AcceptRole)
        # Кнопка: Инструкция
        btn_inst = dialog.addButton("Показать инструкцию", QMessageBox.AcceptRole)
        # Кнопка: Пропустить
        dialog.addButton(QMessageBox.Cancel)
        
        dialog.exec()
        
        if dialog.clickedButton() == btn_gen:
            result = SSHSetupHelper.generate_ssh_key()
            dialog.setInformativeText(result)
            dialog.exec()
        elif dialog.clickedButton() == btn_copy:
            result = SSHSetupHelper.copy_key_to_host(
                os.getenv("SERVER_USER", "yuri"),
                os.getenv("SSH_HOST", "rtx")
            )
            dialog.setInformativeText(result)
            dialog.exec()
        elif dialog.clickedButton() == btn_inst:
            instructions = SSHSetupHelper.get_sudoers_instructions()
            dialog.setDetailedText(instructions)
            dialog.exec()

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
```

### Файл: `scanner_widget.py`

```py
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
```

