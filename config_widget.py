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

from locale_manager import locale


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
    # Язык изменён — нужно повторить перевод интерфейса
    language_changed = Signal(str)

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

        self.model_name_label = QLabel(locale.translate('config.model_label'))
        self.model_name_edit = QLineEdit()
        self.model_name_edit.setReadOnly(True)

        self.size_label = QLabel()
        self.size_label.setStyleSheet("color: grey; font-size: 12px;")

        left_top_layout.addWidget(self.model_name_label)
        left_top_layout.addWidget(self.model_name_edit, 1)  # Поле ввода забирает ВСЁ доступное пространство
        left_top_layout.addWidget(self.size_label)

        # Правая часть (будет строго над правым сплиттером)
        right_top_part = QWidget()
        right_top_layout = QHBoxLayout(right_top_part)
        right_top_layout.setContentsMargins(10, 0, 0, 0)
        right_top_layout.setSpacing(0)

        self.button_modfiles = QPushButton("Обзор")
        self.button_modfiles.clicked.connect(self._browse_mods_directory)

        self.mods_path_label = QLabel()
        self._update_mods_path_label()
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
        self.output_table.setHorizontalHeaderLabels([
            locale.translate('config.col_name'),
            locale.translate('config.col_folder'),
            locale.translate('config.col_date'),
        ])
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

        self.button_clear = QPushButton(locale.translate('config.clear'))
        self.button_get = QPushButton(locale.translate('config.load'))
        self.button_save = QPushButton(locale.translate('config.save'))
        self.button_manage = QPushButton(locale.translate('config.manage'))

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

        self.model_name_edit.setPlaceholderText(locale.translate('config.model_placeholder'))
        self.text_edit_left.setPlaceholderText(locale.translate('config.left_placeholder'))
        self.text_edit_right.setPlaceholderText(locale.translate('config.right_placeholder'))

    def _browse_mods_directory(self):
        directory = QFileDialog.getExistingDirectory(
            self, locale.translate('config.browse_mods_title'), self.mods_path or ""
        )
        if not directory:
            return

        self.mods_path = directory
        # Обновляем отображение пути
        self._update_mods_path_label()
        try:
            from dotenv import set_key
            set_key(self._env_path, "LAST_MODS_PATH", self.mods_path)
            logging.info(f"[CW] Каталог модов сохранён в .env: {self.mods_path}")
        except Exception as e:
            logging.error(f"[CW] Не удалось сохранить LAST_MODS_PATH в .env: {e}")
            QMessageBox.warning(self, locale.translate('common.warning'),
                                 f"{locale.translate('config.not_saved')}\n{e}")

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
        self.size_label.setText(f"{model_size_gb:.3f} {locale.translate('config.gb')}")

        base = model_name.rsplit(".", 1)[0]
        mods = self._find_mods_for_base(base)

        if mods:
            self._populate_table(mods)
            self.text_edit_left.clear()
            self.text_edit_right.clear()
            self._current_mod_file_path = None
            self.button_get.setText(locale.translate('config.load'))
            self.button_get.setEnabled(False)
        else:
            # Если файла настроек нет — генерируем полный шаблон
            self._populate_table([])
            self.text_edit_right.clear()
            self._current_mod_file_path = None

            content = self._generate_auto_config(model_name, self.model_size)
            self.text_edit_left.setPlainText(content)

            self.button_get.setText(locale.translate('config.load'))
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
            self.button_get.setText(locale.translate('config.load'))
            self.button_get.setEnabled(True)
        except Exception as e:
            self.text_edit_left.setPlainText(str(e))

    def on_get_clicked(self):
        self.text_edit_right.setPlainText(self.text_edit_left.toPlainText())

    def on_clear_clicked(self):
        self.text_edit_left.clear()
        self.text_edit_right.clear()
        self._current_mod_file_path = None
        self.button_get.setText(locale.translate('config.load'))
        self.button_get.setEnabled(False)

    def on_save_config_clicked(self):
        content_to_save = self.text_edit_right.toPlainText().strip()
        if not content_to_save:
            QMessageBox.warning(self, locale.translate('common.error'), locale.translate('config.no_data'))
            return

        default_name = "config"
        if self._current_mod_file_path:
            default_name = os.path.splitext(os.path.basename(self._current_mod_file_path))[0]
        else:
            model_name = self.model_name_edit.text().strip()
            if model_name:
                default_name = os.path.splitext(model_name)[0]

        if not self.mods_path:
            QMessageBox.warning(self, locale.translate('common.error'), locale.translate('config.no_path'))
            return
        initial_path = os.path.join(self.mods_path, f"{default_name}.mod")
        file_path, accepted = QFileDialog.getSaveFileName(
            self, locale.translate('config.save_title'), initial_path,
            f"{locale.translate('config.save_filter')};;{locale.translate('config.all_files')}"
        )
        if not accepted:
            return
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content_to_save)
            QMessageBox.information(self, locale.translate('common.success'), locale.translate('config.saved_ok'))
            self.start_scan()
        except Exception as e:
            QMessageBox.critical(self, locale.translate('common.error'), str(e))

    def on_manage_clicked(self):
        command_string = self.text_edit_right.toPlainText().strip()
        if command_string:
            self.run_command_requested.emit(command_string)

    # ---------------------------------------------------------
    #  Локализация интерфейса
    # ---------------------------------------------------------
    def _update_mods_path_label(self):
        self.mods_path_label.setText(f"{locale.translate('config.dir_prefix')} {self.mods_path}")

    def retranslate(self):
        self.model_name_label.setText(locale.translate('config.model_label'))
        # Единица размера локализована; model_size хранится в МБ, 1024 —
        # степень двойки, поэтому обратное деление даёт ровно исходное значение
        if self.model_size is not None:
            self.size_label.setText(f"{self.model_size / 1024:.3f} {locale.translate('config.gb')}")
        self.button_modfiles.setText(locale.translate('config.browse'))
        self._update_mods_path_label()
        self.button_clear.setText(locale.translate('config.clear'))
        self.button_get.setText(locale.translate('config.load'))
        self.button_save.setText(locale.translate('config.save'))
        self.button_manage.setText(locale.translate('config.manage'))

        self.output_table.setHorizontalHeaderLabels([
            locale.translate('config.col_name'),
            locale.translate('config.col_folder'),
            locale.translate('config.col_date'),
        ])

        self.model_name_edit.setPlaceholderText(locale.translate('config.model_placeholder'))
        self.text_edit_left.setPlaceholderText(locale.translate('config.left_placeholder'))
        self.text_edit_right.setPlaceholderText(locale.translate('config.right_placeholder'))

