# server_control.py

import logging

# Настройка логгера
logger = logging.getLogger(__name__)


class ServerControl:
    """Минимальная заглушка для обратной совместимости импорта.

    Все методы класса (stop_server, get_system_stats, extract_model,
    is_running, clear, set_model) ранее были мёртвыми кодом — ни один из них
    не вызывался нигде. Функциональность, которую они дублировали, реализована
    в services/system_monitor.py (RemoteMonitorThread: процессы llama-server,
    метрики, извлечение модели) и в server_widget.py/llmctl (остановка сервера).

    main_ui.py создаёт объект только ради импорта:
        self.server_control: ServerControl = ServerControl()
    Поэтому оставляем пустой __init__, чтобы не ломать сборку.

    Если понадобится локальный контроль процессов на основе psutil — дописать
    методы заново (скелет был в _replacements/services_server_control.py).
    """

    def __init__(self) -> None:
        """Инициализация контроллера сервера."""
        pass
