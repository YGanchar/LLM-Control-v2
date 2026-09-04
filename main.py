# main.py
import sys
import os
import signal
import logging
from PySide6.QtWidgets import QApplication, QMessageBox

# Настройка логирования (выполняется до импорта тяжелых модулей, force=True переопределяет все предыдущие handlers)
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    force=True
)
logging.getLogger("paramiko").setLevel(logging.WARNING)

def load_environment(base_dir):
    """Загрузка переменных окружения из .env файла."""
    env_path = os.path.join(base_dir, ".env")
    if os.path.exists(env_path):
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
            logging.info(f"[MAIN] .env загружен из {env_path}.")
            return True
        except ImportError:
            logging.warning("[MAIN] Библиотека 'python-dotenv' не установлена.")
        except Exception as e:
            logging.error(f"[MAIN] Ошибка при загрузке .env: {e}")
    else:
        logging.warning(f"[MAIN] Файл .env не найден по пути {env_path}.")
    return False

def main():
    # Определяем базовую директорию приложения
    base_dir = os.path.dirname(os.path.abspath(__file__))
    logging.info(f"[MAIN] Запуск приложения. Директория: {base_dir}")

    load_environment(base_dir)

    app = QApplication(sys.argv)

    # Жёсткое убийство процесса (SIGTERM/SIGINT) не вызывает closeEvent, поэтому
    # QThread мониторинга уничтожается во время работы — это вызывает сбой.
    # Перехватываем сигналы и завершаем приложение чисто: app.quit() запускает
    # closeEvent, который штатно останавливает и ждёт поток мониторинга.
    def _graceful_exit(signum, frame):
        logging.info(f"[MAIN] Сигнал {signum} — завершаем работу.")
        app.quit()

    try:
        signal.signal(signal.SIGTERM, _graceful_exit)
        signal.signal(signal.SIGINT, _graceful_exit)
    except (ValueError, OSError):
        # Не в основном потоке или платформа не поддерживает — оставляем поведение по умолчанию
        pass

    try:
        # Импорт внутри try, чтобы перехватить ошибки отсутствующих зависимостей UI
        from main_ui import MainWindow
        main_window = MainWindow()
        main_window.show()
    except ImportError as e:
        error_msg = f"Критическая ошибка импорта модулей интерфейса:\n{e}"
        logging.critical(f"[MAIN] {error_msg}")
        # Показываем окно ошибки пользователю, прежде чем закрыться
        QMessageBox.critical(None, "Ошибка запуска", error_msg)
        sys.exit(1)
    except Exception as e:
        error_msg = f"Непредвиденная ошибка при запуске:\n{e}"
        logging.exception("[MAIN] Ошибка") # exception запишет traceback в лог
        QMessageBox.critical(None, "Ошибка", error_msg)
        sys.exit(1)

    # В PySide6 рекомендуется использовать sys.exit(app.exec()) 
    # для корректного завершения процесса при закрытии окна
    sys.exit(app.exec())

if __name__ == '__main__':
    main()