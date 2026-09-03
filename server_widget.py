# server_widget.py

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

# Поиск SSH-ключа для беспарольного доступа
def _get_ssh_key_path() -> str:
    """Ищет первый доступный SSH-ключ."""
    key_paths = [
        "~/.ssh/id_ed25519_llm",
        "~/.ssh/id_ed25519",
        "~/.ssh/id_rsa",
    ]
    for kp in key_paths:
        expanded = os.path.expanduser(kp)
        if os.path.exists(expanded):
            return expanded
    return ""

SSH_KEY = _get_ssh_key_path()
if SSH_KEY:
    logging.info(f"[ServerWidget] Используется SSH-ключ: {SSH_KEY}")
else:
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
        self.btn_wol.setFixedSize(130, 36) # Компактный фиксированный размер
        
        self.btn_shutdown = QPushButton("Выключить (SSH)")
        self.btn_shutdown.setStyleSheet("background-color: #bd2130; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_shutdown.setFixedSize(130, 36)
        
        power_buttons_layout.addWidget(self.btn_wol)
        power_buttons_layout.addWidget(self.btn_shutdown)
        power_buttons_layout.addStretch() # Прижимаем кнопки к верхнему краю зоны
        
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
            btn.setFixedHeight(30) # Исправлено с setHeight
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
        
        # Проверка SSH-ключа перед выполнением
        if not SSH_KEY:
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
        
        # Формируем аргументы SSH с явным указанием ключа
        ssh_args = [
            "-i", SSH_KEY,
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=5",
            SSH_HOST,
            f"sudo /usr/local/bin/llmctl {full_action}"
        ]
        
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
        elif dialog.clickedButton() == btn_copy:
            result = SSHSetupHelper.copy_key_to_host(
                os.getenv("SERVER_USER", "yuri"),
                os.getenv("SSH_HOST", "rtx")
            )
        elif dialog.clickedButton() == btn_inst:
            instructions = SSHSetupHelper.get_sudoers_instructions()
            dialog.setDetailedText(instructions)
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