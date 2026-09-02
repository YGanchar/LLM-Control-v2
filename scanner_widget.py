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