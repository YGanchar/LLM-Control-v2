# scanner_widget.py
# -*- coding: utf-8 -*-
import os
import sys
import json
import logging
from typing import List, Tuple, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QLabel, QLineEdit, QFileDialog, QHeaderView,
    QProgressBar, QSizePolicy, QMessageBox, QComboBox
)
from PySide6.QtCore import Qt, Signal, QRect, QSize, Slot, QTimer
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


def _all_locale_texts(key: str) -> List[str]:
    """Перевод ключа key для всех доступных локалей (*.json в locales/).

    Используется, чтобы задать размер элементов UI по максимуму — тогда при
    смене языка размеры и расположение виджетов не меняются."""
    texts: List[str] = []
    try:
        locales_dir = locale.locales_dir
        names = sorted(os.listdir(locales_dir))
    except OSError:
        return texts
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(locales_dir, name), "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        text = data.get(key, key)
        if text:
            texts.append(text)
    return texts


def _read_conf_model(config_path: str) -> Optional[str]:
    """Возвращает значение MODEL= из конфига запуска (.conf) или None.

    В конфиге путь записан как «/srv/models/...» (шаблонный), поэтому
    сопоставление с реальными файлами ниже идёт по имени (basename)."""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("MODEL="):
                    value = line[len("MODEL="):].strip().strip('"').strip("'")
                    return value or None
    except OSError as e:
        logging.error(f"[SW] Не удалось прочитать конфиг {config_path}: {e}")
    return None


class WrappingBar(QWidget):
    """Переносяющаяся строка управления на базе QWidget (не QLayout).

    QLayout-раскладки в PySide6 6.11 не вызываются C++-движком раскладки:
    переопределения sizeHint/minimumSize игнорируются, а политику растягивания
    задать нельзя — в результате раскладка растЯгивается по вертикали и сжимает
    таблицу. У QWidget sizeHint, resizeEvent и set работают штатно, поэтому
    перенос элементов по строкам делаем в resizeEvent этого виджета. По
    вертикали виджет не растягивается — вся оставшаяся высота вкладки
    достаётся таблице."""

    def __init__(self, parent=None, margin=0, spacing=6):
        super().__init__(parent)
        self._margin = int(margin)
        self._spacing = int(spacing) if spacing >= 0 else 6
        self._widgets = []
        # Строка занимает только свою высоту, по ширине — всю доступную.
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def addWidget(self, widget):
        if widget is not None:
            widget.setParent(self)
            self._widgets.append(widget)

    def addStretch(self) -> None:
        """Добавляет растягиваемый разделитель. Элементы, стоящие после него,
        в каждой строке прижимаются к правому краю (разделитель занимает всё
        свободное место своей строки)."""
        marker = QWidget(self)
        marker.setProperty("_is_stretch", True)
        marker.setFixedSize(0, 0)
        self._widgets.append(marker)

    def _is_stretch(self, widget) -> bool:
        return bool(widget is not None and widget.property("_is_stretch"))

    def _do_layout(self) -> None:
        rect = self.contentsRect()
        margin = self._margin
        spacing = self._spacing

        # Индекс последнего разделителя (если есть): всё, что после него,
        # нужно прижать к правому краю на его строке.
        last_stretch = -1
        for i, widget in enumerate(self._widgets):
            if self._is_stretch(widget):
                last_stretch = i

        # Первый проход: раскладка слева направо с переносом, разделители пропущены.
        placed = []  # (index, x, y, width, height)
        x = rect.left() + margin
        y = rect.top()
        line_height = 0
        for i, widget in enumerate(self._widgets):
            if widget is None or not widget.isVisible() or self._is_stretch(widget):
                continue
            width = widget.sizeHint().width()
            width = min(width, widget.maximumSize().width())
            width = max(width, widget.minimumSize().width())

            # Если элемент не влезает в текущую строку — переносим её.
            if x + width > rect.right() and x > rect.left() + margin:
                x = rect.left() + margin
                y += line_height + spacing
                line_height = 0

            height = widget.sizeHint().height()
            placed.append((i, x, y, width, height))
            x += width + spacing
            line_height = max(line_height, height)

        # Разобьём размещённые виджеты по строкам (по y) и найдём высоту каждой
        # строки — по самому высокому виджету. Она нужна, чтобы центрировать по
        # вертикали виджеты ниже максимальной высоты строки (например, метки).
        lines = {}  # y -> [placed items]
        for item in placed:
            lines.setdefault(item[2], []).append(item)
        line_heights = {ly: max(it[4] for it in its) for ly, its in lines.items()}

        # Ставим виджет на вычисленную позицию, центрируя его по вертикали
        # внутри строки. Сдвиг (shift) применяется ко второму проходу — вправо.
        def place(idx, px, py, pw, ph, shift=0):
            offset = (line_heights[py] - ph) // 2
            self._widgets[idx].setGeometry(QRect(px + shift, py + offset, pw, ph))

        # Первый проход теперь реально расставляет виджеты — до этой правки
        # позиции только вычислялись в placed и применялись лишь к «хвосту»,
        # из-за чего лево-виджеты оставались в (0,0) и накладывались друг на
        # друга (например, «Сохранить список» поле пути поверх него).
        for (idx, px, py, pw, ph) in placed:
            place(idx, px, py, pw, ph)

        # Второй проход: виджеты после последнего разделителя прижаем вправо
        # как единый блок на их строке (чтобы группа языка не «прилипала» к
        # левому краю и не наезжала друг на друга). Сдвиг единый для всей
        # строки — сохраняются промежутки между виджетами блока.
        if last_stretch >= 0:
            trailing = {id(w) for w in self._widgets[last_stretch + 1:]}
            for items in lines.values():
                right_items = [it for it in items if id(self._widgets[it[0]]) in trailing]
                if not right_items:
                    continue
                block_right = max(px + pw for (idx, px, py, pw, ph) in right_items)
                shift = (rect.right() - margin) - block_right
                if not shift:
                    continue
                for (idx, px, py, pw, ph) in right_items:
                    place(idx, px, py, pw, ph, shift=shift)

    def showEvent(self, event):
        super().showEvent(event)
        # Размер виджета уточняется родителем уже после показа, поэтому
        # пересчитываем раскладку в следующем цикле событий — когда размеры
        # уже известны. Иначе в некоторых платформах (в т.ч. offscreen)
        # resizeEvent не доводит раскладку до конца и виджеты остаются
        # наложенными в (0,0).
        QTimer.singleShot(0, self._do_layout)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._do_layout()

    def sizeHint(self):
        width = 0
        height = 0
        for widget in self._widgets:
            width += widget.sizeHint().width() + self._spacing
            height = max(height, widget.sizeHint().height())
        return QSize(width, height)

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
        # Модель, выбранная по двойному клику (фолбэк при автовыделении).
        self.last_selected_path = os.getenv("LAST_MODEL_PATH") or ""

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
        # Используется переносящийся виджет WrappingBar, чтобы при сужении
        # окна комбобокс «Язык» переносился на новую строку, а не вытеснял
        # кнопки за пределы окна. Поле пути ограничено по ширине, чтобы все
        # элементы (кнопки и комбобокс «Язык») помещались в одну строку.
        # По вертикали виджет не растягивается — таблица занимает всю
        # оставшуюся высоту вкладки.
        self.top_layout = WrappingBar()

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

        self.top_layout.addWidget(self.scan_path_label)
        self.top_layout.addWidget(self.scan_path_edit)
        self.top_layout.addWidget(self.browse_button)
        self.top_layout.addWidget(self.scan_button)
        self.top_layout.addWidget(self.save_button)
        # Разделитель: группа языка прижимается к правому краю строки.
        self.top_layout.addStretch()
        self.top_layout.addWidget(self.language_label)
        self.top_layout.addWidget(self.language_combo)

        self.layout.addWidget(self.top_layout)

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

        # Фиксируем размеры элементов строки (по максимуму по всем локалям),
        # чтобы при смене языка размеры и расположение не менялись.
        self._sync_stable_sizes()

        # Автозаполнение таблицы моделями при старте + выделение последней
        # модели (из конфига запуска или выбранной по двойному клику).
        self._auto_populate()

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
            self.models_data = self._build_models_list(raw_files)
            logging.info(f"[Сканер] Найдено: {len(self.models_data)}")

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

    def _build_models_list(self, raw_files):
        """Обрабатывает сырой список найденных файлов в список моделей
        [(full_path, size_gb, has_vision_bool), ...]. Vision-файлы (mmproj/
        clip/vision) не учитываются как модели, но помечают папку как vision."""
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
        return processed_models

    def _auto_populate(self):
        """Заполняет таблицу моделями при старте из LAST_SCAN_PATH (если диск
        доступен) и выделяет последнюю модель — из конфига запуска или
        выбранную по двойному клику. Краш при отсутствии диска не вызывает."""
        if not self.current_scan_path or not os.path.isdir(self.current_scan_path):
            return
        try:
            raw_files = find_files_by_extension(self.current_scan_path, ".gguf")
            self.models_data = self._build_models_list(raw_files)
            self._populate_table(self.models_data)
            self._highlight_last_model()
        except Exception as e:
            logging.error(f"[SW] Автозаполнение не удалось: {e}")

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

    def _resolve_last_model_path(self) -> Optional[str]:
        """Определяет, какую модель выделить при старте. Приоритет:
        1) MODEL= из конфига запуска (DEFAULT_CONFIG_PATH);
        2) фолбэк — модель, выбранная по двойному клику."""
        config_path = os.getenv("DEFAULT_CONFIG_PATH")
        if config_path and os.path.isfile(config_path):
            model = _read_conf_model(config_path)
            if model:
                return model
        last = self.last_selected_path
        if last and os.path.isfile(last):
            return last
        return None

    def _highlight_last_model(self):
        """Выделяет в таблице строку последней модели (по имени файла).
        Путь в конфиге (/srv/models/…) отличается от реального
        (/media/rtx-models/…), поэтому сверка по basename. Только выделение —
        на вкладку «Параметры» не переходим."""
        target = self._resolve_last_model_path()
        if not target:
            return
        for row, (file_path, _, _) in enumerate(self.models_data):
            if os.path.basename(file_path) == os.path.basename(target):
                self.table_widget.setCurrentItem(self.table_widget.item(row, 0))
                logging.info(f"[SW] Выделена модель: {os.path.basename(file_path)}")
                return

    @staticmethod
    def _max_hint(texts, builder):
        """Максимальные width/height sizeHint среди всех texts, построенных
        через builder(text). builder нужен, потому что QComboBox не принимает
        текст в конструкторе."""
        w = h = 0
        for text in texts:
            hint = builder(text).sizeHint()
            w = max(w, hint.width())
            h = max(h, hint.height())
        return w, h

    @staticmethod
    def _make_combo_item(text):
        combo = QComboBox()
        combo.addItem(text)
        return combo

    def _sync_stable_sizes(self):
        """Задаём фиксированные размеры элементов строки управления, чтобы при
        смене языка их ширина/высота и расположение не менялись. Ширину каждого
        элемента берём по максимуму среди всех доступных локалей (data-driven).
        Три кнопки — одинаковой ширины."""
        browse_texts = _all_locale_texts('scanner.browse')
        scan_texts = _all_locale_texts('scanner.scan')
        save_texts = _all_locale_texts('scanner.save_list')
        path_texts = _all_locale_texts('scanner.path_label')
        lang_label_texts = _all_locale_texts('config.language_label')
        lang_items = (_all_locale_texts('config.lang_ru')
                      + _all_locale_texts('config.lang_en')
                      + _all_locale_texts('config.lang_es'))

        # Кнопки: одинаковая ширина и высота по максимуму из трёх текстов.
        btn_w, btn_h = self._max_hint(
            browse_texts + scan_texts + save_texts, lambda t: QPushButton(t))
        for btn in (self.browse_button, self.scan_button, self.save_button):
            btn.setFixedWidth(btn_w)
            btn.setFixedHeight(btn_h)

        # Метки — ширина по максимуму по всем локалям.
        self.scan_path_label.setFixedWidth(self._max_hint(path_texts, lambda t: QLabel(t))[0])
        self.language_label.setFixedWidth(
            self._max_hint(lang_label_texts, lambda t: QLabel(t))[0])

        # Комбо языка — ширина по максимуму из названий языков.
        combo_w, combo_h = self._max_hint(lang_items, self._make_combo_item)
        self.language_combo.setFixedWidth(combo_w)
        self.language_combo.setMaximumHeight(combo_h)

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
            self.last_selected_path = full_path
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