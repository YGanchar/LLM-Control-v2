# services/model_scanner.py

import os
from typing import List, Tuple, Generator

def _scan_directory(scan_path: str, extension: str) -> Generator[Tuple[str, int, float], None, None]:
    """
    Общий итеративный обход директории для поиска файлов с заданным расширением.
    """
    if not os.path.isdir(scan_path):
        raise ValueError(f"Invalid directory: {scan_path}")

    ext = extension.lower().strip()
    if ext and not ext.startswith('.'):
        ext = f".{ext}"

    stack = [scan_path]
    while stack:
        current_dir = stack.pop()
        try:
            with os.scandir(current_dir) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            if entry.name.lower().endswith(ext):
                                stat_info = entry.stat()
                                yield (entry.path, stat_info.st_size, stat_info.st_mtime)
                    except (OSError, PermissionError):
                        continue
        except (OSError, PermissionError):
            continue

def find_files_by_extension(scan_path: str, extension: str) -> List[Tuple[str, int, float]]:
    """
    Сканирует директорию на наличие файлов с заданным расширением.
    """
    return list(_scan_directory(scan_path, extension))

def find_files_generator(scan_path: str, extension: str) -> Generator[Tuple[str, int, float], None, None]:
    """
    Версия-генератор для работы с очень большими дисками.
    Позволяет получать файлы по одному, не загружая всё в память.
    """
    return _scan_directory(scan_path, extension)