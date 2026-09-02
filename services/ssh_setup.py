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
