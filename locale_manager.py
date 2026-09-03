# locale_manager.py
# JSON-локализация интерфейса (без .qm Qt).
# Класс LocaleManager + глобальный синглотон `locale`, который используют виджеты.

import os
import sys
import json
import logging

DEFAULT_LANGUAGE = "en"


def _resolve_app_dir() -> str:
    """Диретория приложения: рядом с исполняемым (frozen-сборка PyInstaller)
    или со скриптом (venv). Аналогично _resolve_env_path() в модулях UI."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


class LocaleManager:
    """Загружает словари локализации из /locales/<lang>.json и переводит ключи."""

    def __init__(self) -> None:
        self._translations: dict = {}
        self.current_language: str = DEFAULT_LANGUAGE

    @property
    def locales_dir(self) -> str:
        return os.path.join(_resolve_app_dir(), "locales")

    def _load_file(self, lang_code: str) -> bool:
        """Пытается загрузить словарь языка. Возвращает True при успехе."""
        path = os.path.join(self.locales_dir, f"{lang_code}.json")
        if not os.path.isfile(path):
            logging.warning(
                f"[LOCALE] Локализация не найдена: {path}. "
                f"Fallback на {DEFAULT_LANGUAGE}."
            )
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._translations = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logging.error(f"[LOCALE] Ошибка чтения {path}: {e}. Fallback на {DEFAULT_LANGUAGE}.")
            return False
        logging.info(f"[LOCALE] Загружена локализация: {lang_code} ({path})")
        return True

    def _fallback(self) -> None:
        """Загружает en.json как язык по умолчанию."""
        if not self._load_file(DEFAULT_LANGUAGE):
            self._translations = {}

    def load_locale(self, lang_code: str) -> str:
        """Загружает локализацию по коду языка.

        При ошибке (файл не найден / битый JSON) — fallback на en.json.
        Возвращает фактически загруженный код языка.
        """
        lang_code = (lang_code or "").strip() or DEFAULT_LANGUAGE

        if self._load_file(lang_code):
            self.current_language = lang_code
        else:
            self._fallback()
            self.current_language = DEFAULT_LANGUAGE
        return self.current_language

    def translate(self, key: str) -> str:
        """Возвращает строку по ключу. Если ключ отсутствует — возвращает сам ключ."""
        return self._translations.get(key, key)


# Глобальный синглотон для импорта в модулях UI:
#   from locale_manager import locale
locale = LocaleManager()
