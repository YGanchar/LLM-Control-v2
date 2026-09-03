# -*- coding: utf-8 -*-
"""
Единый менеджер SSH-ключей для проекта LLM-Control.

Выносит общую логику поиска и кэширования SSH-ключа из
system_monitor.py и server_widget.py в одно место (DRY).
"""
import os
import logging
from typing import List, Optional


class SSHManager:
    """
    Синглтон-подобный менеджер SSH-подключений.

    Отвечает за:
    - поиск первый доступный SSH-ключа из списка кандидатов;
    - кэширование найденного пути (чтобы не проверять os.path.exists
      при каждом клике по кнопке);
    - формирование аргументов командной строки для внешнего ssh-клиента
      (QProcess) и для paramiko.
    """

    _cached_key_path: Optional[str] = None
    _key_searched: bool = False

    # Кандидаты на SSH-ключ — от специфичного к общему.
    # Специальный ключ LLM-Control идёт первым, чтобы не конфликтовать
    # с пользовательскими ключами, если они есть.
    _KEY_CANDIDATES: List[str] = [
        "~/.ssh/id_ed25519_llm",  # Специальный ключ для LLM-Control
        "~/.ssh/id_ed25519",       # Стандартный Ed25519
        "~/.ssh/id_rsa",           # Стандартный RSA
    ]

    @classmethod
    def get_ssh_key_path(cls) -> Optional[str]:
        """
        Ищет и кэчирует первый доступный SSH-ключ.

        Возвращает абсолютный путь к ключу или None, если ни один
        из кандидатов не найден. Повторные вызовы возвращают
        закэшированное значение без повторного обращения к ФС.
        """
        if cls._key_searched:
            return cls._cached_key_path

        for kp in cls._KEY_CANDIDATES:
            expanded = os.path.expanduser(kp)
            if os.path.exists(expanded):
                cls._cached_key_path = expanded
                cls._key_searched = True
                logging.info(f"[SSHManager] Найден SSH-ключ: {expanded}")
                return expanded

        cls._key_searched = True
        cls._cached_key_path = None
        logging.warning(
            "[SSHManager] SSH-ключ не найден ни по одному из путей: "
            f"{cls._KEY_CANDIDATES}. "
            "Беспарольный доступ не работает. "
            "Выполните: ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_llm -N '' "
            "&& ssh-copy-id -i ~/.ssh/id_ed25519_llm.pub yuri@rtx"
        )
        return None

    @classmethod
    def get_ssh_base_args(cls, host: str, command: str) -> List[str]:
        """
        Формирует базовые аргументы для запуска внешнего ssh-клиента
        через QProcess.

        Args:
            host: имя хоста или IP (должен резолвиться через ~/.ssh/config
                  или /etc/hosts).
            command: команда, которую нужно выполнить на удалённом хосте.

        Returns:
            Список аргументов для QProcess.start("ssh", args).
            Пустой список, если SSH-ключ не найден (вызывающий код
            должен сам показать диалог настройки).
        """
        key = cls.get_ssh_key_path()
        if not key:
            return []

        return [
            "-i", key,
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=5",
            host,
            command,
        ]

    @classmethod
    def reset_cache(cls) -> None:
        """
        Сбрасывает кэш ключа. Полезно после генерации нового ключа
        через SSHSetupHelper — чтобы следующий вызов get_ssh_key_path()
        увидел свежий файл.
        """
        cls._cached_key_path = None
        cls._key_searched = False
        logging.info("[SSHManager] Кэш SSH-ключа сброшен.")
