# scanner_widget.py
# -*- coding: utf-8 -*-
import os
import sys
import logging
from typing import List, Tuple

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QLabel, QLineEdit, QFileDialog, QHeaderView,
    QProgressBar, QSizePolicy, QMessageBox, QComboBox, QLayout,
    QWidgetItem, QLayoutItem
)
from PySide6.QtCore import Qt, Signal, QRect, QSize, Slot
from PySide6.QtGui import QBrush, QColor, QFont

from dotenv import set_key
from locale_manager import locale

# Предполагаем наличие этого модуля в проекте
try:
    from services.model_scanner import find_files_by_extension
except ImportError:
    logging.error("Модуль services.model_scanner не найден")
    def find_files_by_extension(*args): return []


def _resolve_env_path() -> str:
    """.env рядом с исполняемым файлом (frozen-сборка) или со скриптом (Thonny/venv) -
    не зависит от текущей рабочей директории процесса."""
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, ".env")


class WrappingLayout(QLayout):
    """Раскладывает элементы по строкам и переносит на новую строку, когда
    текущая строка заполнена. Используется для строки «Путь сканирования»,
    чтобы при сужении окна комбобокс «Язык» переносился на следующую строку,
    а не вытеснял кнопки за пределы окна."""

    def __init__(self, parent=None, margin=0, spacing=-1):
        super().__init__(parent)
        self._margin = int(margin)
        self._spacing = int(spacing) if spacing >= 0 else 6
        self._items = []

    def __del__(self):
        # PySide6 сам управляет C++-жизнью раскладки и её элементов.
        # Здесь только сбрасываем Python-список, чтобы не держать лишние ссылки.
        self._items.clear()

    def addWidget(self, widget):
        if widget is not None:
            self.addItem(QWidgetItem(widget))

    def addLayout(self, layout):
        if layout is not None:
            self.addItem(QLayoutItem(layout))

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Horizontal | Qt.Vertical

    def hasSizeHint(self):
        return True

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return QSize(size.width() + 2 * self._margin, size.height() + 2 * self._margin)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        if self.count() == 0:
            return
        self._do_layout(rect)

    def _do_layout(self, rect: QRect) -> None:
        top = rect.top()
        x = rect.x()
        y = rect.y()
        line_height = 0

        for item in self._items:
            widget = item.widget()
            if widget is None or not widget.isVisible():
                continue

            width = item.sizeHint().width()
            width = min(width, item.maximumSize().width())
            width = max(width, item.minimumSize().width())

            # Если элемент не влезает в текущую строку — переносим её.
            if x + width > rect.right() and x > rect.x():
                x = rect.x()
                y = top + line_height + self._spacing
                line_height = 0

            height = item.sizeHint().height()
            height = min(height, item.maximumSize().height())
            height = max(height, item.minimumSize().height())

            item.setGeometry(QRect(x, y, width, height))
            x += width + self._spacing
            line_height = max(line_height, height)

class ScannerWidget(QWidget):
    scan_started = Signal()
    scan_finished = Signal(list)  # List[Tuple[str, float]] - (путь, размер)
    model_selected = Signal(str, float)   # (путь, размер)
    # Язык изменён — нужно повторить перевод интерфейса (сигнал ловит main_ui)
    language_changed = Signal(str)
 
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_widget = parent
        self.current_scan_path = os.getenv("LAST_SCAN_PATH") or ""
        self.current_save_path = os.getenv("LAST_SAVE_PATH") or ""
        self.llama_path = os.getenv("LLAMA_PATH") or ""

        # Путь к .env для сохранения выбранного языка
        self._env_path = _resolve_env_path()

        # Структура данных: [(full_path, size_gb, has_vision_bool), ...]
        self.models_data: List[Tuple[str, float, bool]] = []
        self._sort_states: dict = {}  # {column_index: ascending_bool}
        self._init_ui()

    def _init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)

        # Единая строка: путь сканирования + кнопки + выбор языка.
        # Используется переносящая раскладка (WrappingLayout), чтобы при сужении
        # окна комбобокс «Язык» переносился на новую строку, а не вытеснял
        # кнопки за пределы окна. Поле пути ограничено по ширине, чтобы все
        # элементы (кнопки и комбобокс «Язык») помещались в одну строку.
        self.top_layout = WrappingLayout()
        self.top_layout.setContentsMargins(0, 0, 0, 0)
        self.top_layout.setSpacing(6)

        self.scan_path_label = QLabel(locale.translate('scanner.path_label'))
        self.scan_path_edit = QLineEdit(self.current_scan_path)
        self.scan_path_edit.setReadOnly(True)
        self.scan_path_edit.setMinimumWidth(160)
        self.scan_path_edit.setMaximumWidth(320)

        self.browse_button = QPushButton(locale.translate('scanner.browse'))
        self.browse_button.clicked.connect(self._browse_directory)

        self.scan_button = QPushButton(locale.translate('scanner.scan'))
        self.scan_button.clicked.connect(self.start_scan)
        self.save_button = QPushButton(locale.translate('scanner.save_list'))
        self.save_button.clicked.connect(self.save_sorted_list)

        # Строка выбора языка (перенесена со вкладки «Параметры модели»)
        self.language_label = QLabel(locale.translate('config.language_label'))
        self.language_combo = QComboBox()
        self._populate_language_combo()
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        self.language_combo.setMaximumWidth(140)

        self.top_layout.addWidget(self.scan_path_label)
        self.top_layout.addWidget(self.scan_path_edit)
        self.top_layout.addWidget(self.browse_button)
        self.top_layout.addWidget(self.scan_button)
        self.top_layout.addWidget(self.save_button)
        self.top_layout.addWidget(self.language_label)
        self.top_layout.addWidget(self.language_combo)

        self.layout.addLayout(self.top_layout)

        # Прогресс-бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.layout.addWidget(self.progress_bar)

        # Таблица
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(3)
        self.table_widget.setHorizontalHeaderLabels([
            locale.translate('scanner.col_name'),
            locale.translate('scanner.col_size'),
            locale.translate('scanner.col_vision'),
        ])
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
        directory = QFileDialog.getExistingDirectory(
            self,
            locale.translate('scanner.browse_title'),
            self.current_scan_path,
        )
        if directory:
            self.current_scan_path = directory
            self.scan_path_edit.setText(self.current_scan_path)

    def start_scan(self):
        if not self.current_scan_path or not os.path.isdir(self.current_scan_path):
            QMessageBox.warning(
                self,
                locale.translate('common.error'),
                locale.translate('scanner.path_not_exist'),
            )
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
            QMessageBox.critical(
                self,
                locale.translate('common.error'),
                f"{locale.translate('scanner.scan_error')}\n{str(e)}",
            )
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
            item_vision = QTableWidgetItem(locale.translate('scanner.vision_yes') if has_vision else "")
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
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            locale.translate('scanner.save_title'),
            "",
            locale.translate('scanner.save_filter'),
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as file:
                    for path, size, vision in self.models_data:
                        v_flag = "[Vision]" if vision else ""
                        file.write(f"{os.path.basename(path)}, {size:.2f} GB {v_flag}\n")
            except Exception as e:
                QMessageBox.warning(
                    self,
                    locale.translate('common.error'),
                    f"{locale.translate('scanner.save_error')}{e}",
                )

    def on_model_double_clicked(self, item):
        row = item.row()
        if row < len(self.models_data):
            full_path, size_gb, _ = self.models_data[row]
            logging.info(f"[SW] Выбрана модель: {full_path}")
            self.model_selected.emit(full_path, size_gb)

    def _populate_language_combo(self):
        """Заполняет комбо языков переведёчными названиями и выделяет текущий."""
        self.language_combo.blockSignals(True)
        self.language_combo.clear()
        for code, name_key in (("ru", "config.lang_ru"), ("en", "config.lang_en"), ("es", "config.lang_es")):
            self.language_combo.addItem(locale.translate(name_key), code)
        index = self.language_combo.findData(locale.current_language)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)
        self.language_combo.blockSignals(False)

    @Slot(int)
    def _on_language_changed(self, _index: int):
        code = self.language_combo.currentData()
        if not code or code == locale.current_language:
            return
        locale.load_locale(code)
        set_key(self._env_path, "LANGUAGE", code)
        self.language_changed.emit(code)

    def retranslate(self) -> None:
        """Перекладываем статические элементы без пересоздания виджетов/данных."""
        self.language_label.setText(locale.translate('config.language_label'))
        # Повторно показываем перевод языков в комбо (с заблокированными
        # сигналами — смена языка при перекладывании не запускается).
        self._populate_language_combo()
        self.scan_path_label.setText(locale.translate('scanner.path_label'))
        self.browse_button.setText(locale.translate('scanner.browse'))
        self.scan_button.setText(locale.translate('scanner.scan'))
        self.save_button.setText(locale.translate('scanner.save_list'))
        self.table_widget.setHorizontalHeaderLabels([
            locale.translate('scanner.col_name'),
            locale.translate('scanner.col_size'),
            locale.translate('scanner.col_vision'),
        ])
        # Перекладываем только ячейки «Есть» в колонке Vision (остальные данные — нет)
        vision_yes = locale.translate('scanner.vision_yes')
        for row_index, (_, _, has_vision) in enumerate(self.models_data):
            item = self.table_widget.item(row_index, 2)
            if item is not None:
                item.setText(vision_yes if has_vision else "")