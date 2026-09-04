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

from locale_manager import locale


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
        "label_key": "server.instance_1",
        "config_path": os.getenv("DEFAULT_CONFIG_PATH", "/media/rtx-storage/llama-mode.conf"),
        "llmctl_suffix": "",
    },
    "8081": {
        "label_key": "server.instance_2",
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
        self.controlled_label = QLabel(locale.translate('server.managing'))
        instance_layout.addWidget(self.controlled_label)
        self.instance_group = QButtonGroup(self)
        self.instance_radios = {}
        for key, info in INSTANCES.items():
            rb = QRadioButton(locale.translate(info["label_key"]))
            rb.setChecked(key == self.current_instance)
            rb.toggled.connect(lambda checked, k=key: self._on_instance_changed(k, checked))
            self.instance_group.addButton(rb)
            self.instance_radios[key] = rb
            instance_layout.addWidget(rb)
        instance_layout.addStretch()
        main_layout.addLayout(instance_layout)

        # Сплиттер для разделения логов и зоны управления
        self.splitter = QSplitter(Qt.Vertical, self)

        # Верхнее текстовое поле (Логи / Статус)
        self.server_log_text_edit = QTextEdit()
        self.server_log_text_edit.setReadOnly(True)
        self.server_log_text_edit.setFont(QFont("DejaVu Sans Mono", 10))
        self.server_log_text_edit.setPlaceholderText(locale.translate('server.log_placeholder'))

        # Нижний виджет-контейнер, объединяющий поле ввода и цветные кнопки
        bottom_container = QWidget()
        bottom_layout = QHBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(10)

        # Поле конфигурации
        self.command_text_edit = QTextEdit()
        self.command_text_edit.setFont(QFont("DejaVu Sans Mono", 10))
        self.command_text_edit.setPlaceholderText(locale.translate('server.cmd_placeholder'))

        # Вертикальный блок для цветных кнопок питания (справа от поля ввода)
        power_buttons_layout = QVBoxLayout()
        power_buttons_layout.setContentsMargins(0, 0, 0, 0)
        power_buttons_layout.setSpacing(8)
        self.btn_wol = QPushButton(locale.translate('server.wol'))
        self.btn_wol.setStyleSheet("background-color: #1e7e34; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_wol.setFixedSize(130, 36)  # Компактный фиксированный размер
        self.btn_shutdown = QPushButton(locale.translate('server.shutdown'))
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
            ("apply", "common.apply", self.set_config_file),
            ("start", "common.start", self.start_llama_server),
            ("stop", "common.stop", self.stop_llama_server),
            ("restart", "common.restart", self.restart_llama_server),
            ("status", "common.status", self.show_server_status),
            ("config", "common.config", self.show_llama_mode_conf),
            ("logs", "common.logs", self.show_server_logs)
        ]
        self.control_buttons = {}
        for key, text_key, handler in button_specs:
            btn = QPushButton(locale.translate(text_key))
            btn.clicked.connect(handler)
            btn.setFixedHeight(30)  # Исправлено с setHeight
            self.control_buttons[key] = btn
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
        self.server_log_text_edit.append(f"{locale.translate('log.power')} {msg}")
        self.server_log_text_edit.ensureCursorVisible()

    def _trigger_power_action(self, method, name):
        self.server_log_text_edit.append(
            f"{locale.translate('log.power')} {locale.translate('server.power_executing')} {name}..."
        )
        method()

    def update_command_display(self, command_string):
        self.command_text_edit.setPlainText(command_string)

    def _on_instance_changed(self, key, checked):
        if checked:
            self.current_instance = key
            self.server_log_text_edit.append(
                f"{locale.translate('log.system')} Переключено на {locale.translate(INSTANCES[key]['label_key'])}"
            )

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
            dialog = QMessageBox(self)
            dialog.setWindowTitle(locale.translate('server.ssh_key_missing'))
            dialog.setText(locale.translate('server.ssh_key_missing_msg'))
            btn_yes = dialog.addButton(locale.translate('common.yes'), QMessageBox.AcceptRole)
            dialog.addButton(locale.translate('common.no'), QMessageBox.DestructiveRole)
            dialog.exec()
            if dialog.clickedButton() is not btn_yes:
                self._show_ssh_setup_wizard()
            return

        self.stop_current_stream()
        suffix = INSTANCES[self.current_instance]["llmctl_suffix"]
        full_action = f"{action_arg}{suffix}"
        if clear_output:
            self.server_log_text_edit.clear()
        self.server_log_text_edit.append(
            f"{locale.translate('server.cmd_sending').format(full_action=full_action, ssh_host=SSH_HOST)}\n"
        )

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
                self.server_log_text_edit.insertPlainText(f"\n{locale.translate('log.critical')} {data}\n")
            else:
                self.server_log_text_edit.insertPlainText(f"\n{locale.translate('log.info')} {data}")
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
            self.server_log_text_edit.append(f"{locale.translate('log.error')} {locale.translate('server.cmd_cancelled')}")
            return

        proc.start("ssh", ssh_args)
        if proc.state() == QProcess.NotRunning:
            self.server_log_text_edit.append(f"{locale.translate('log.error')} {locale.translate('server.cmd_start_failed')}")
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
        dialog.setWindowTitle(locale.translate('server.ssh_title'))
        dialog.setText(locale.translate('server.ssh_text'))
        dialog.setInformativeText(locale.translate('server.ssh_inform'))
        btn_gen = dialog.addButton(locale.translate('server.ssh_btn_gen'), QMessageBox.AcceptRole)
        btn_copy = dialog.addButton(locale.translate('server.ssh_btn_copy'), QMessageBox.AcceptRole)
        btn_inst = dialog.addButton(locale.translate('server.ssh_btn_inst'), QMessageBox.AcceptRole)
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
        dialog = QMessageBox(self)
        dialog.setWindowTitle(action_title)
        dialog.setText(message)
        btn_yes = dialog.addButton(locale.translate('common.yes'), QMessageBox.AcceptRole)
        dialog.addButton(locale.translate('common.no'), QMessageBox.DestructiveRole)
        # exec() возвращает код QDialog, а не кнопку: сравнение с btn_yes
        # всегда давало False и подтверждение молча игнорировалось.
        dialog.exec()
        return dialog.clickedButton() is btn_yes

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
            QMessageBox.warning(self, locale.translate('common.warning'), locale.translate('server.config_empty'))
            return
        issues = self._validate_config(raw_content)
        if issues:
            details = "\n".join(f"• {i}" for i in issues)
            dialog = QMessageBox(self)
            dialog.setWindowTitle(locale.translate('server.problems_title'))
            dialog.setText(f"{details}\n\n{locale.translate('server.problems_keep')}")
            btn_yes = dialog.addButton(locale.translate('common.yes'), QMessageBox.AcceptRole)
            dialog.addButton(locale.translate('common.no'), QMessageBox.DestructiveRole)
            dialog.exec()
            if dialog.clickedButton() is not btn_yes:
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
            msg = f"{locale.translate('log.system')} {locale.translate('server.saved_ok').format(path=target_path, instance=locale.translate(INSTANCES[self.current_instance]['label_key']))}\n"
            if info_count > 0:
                msg += f"{locale.translate('log.system')} {locale.translate('server.saved_info').format(count=info_count)}\n"
            msg += locale.translate('server.saved_notice')
            self.server_log_text_edit.setText(msg)
        except Exception as e:
            QMessageBox.critical(self, locale.translate('common.error'), f"{locale.translate('server.write_error')} {str(e)}")

    def _instance_label(self):
        return locale.translate(INSTANCES[self.current_instance]["label_key"])

    def retranslate(self):
        """Перекрасить весь виджет без пересоздания виджетов (смена языка)."""
        self.controlled_label.setText(locale.translate('server.managing'))
        for key, rb in self.instance_radios.items():
            rb.setText(locale.translate(INSTANCES[key]["label_key"]))
        self.btn_wol.setText(locale.translate('server.wol'))
        self.btn_shutdown.setText(locale.translate('server.shutdown'))
        for key, btn in self.control_buttons.items():
            btn.setText(locale.translate(f"common.{key}"))

    def start_llama_server(self):
        if self.confirm_action(
            locale.translate('server.confirm_start_title'),
            locale.translate('server.confirm_start_msg').format(instance=self._instance_label())
        ):
            self.run_async_ssh_cmd("start")

    def stop_llama_server(self):
        if self.confirm_action(
            locale.translate('server.confirm_stop_title'),
            locale.translate('server.confirm_stop_msg').format(instance=self._instance_label())
        ):
            self.run_async_ssh_cmd("stop")

    def restart_llama_server(self):
        if self.confirm_action(
            locale.translate('server.confirm_restart_title'),
            locale.translate('server.confirm_restart_msg').format(instance=self._instance_label())
        ):
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