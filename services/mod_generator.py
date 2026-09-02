"""
mod_generator.py

Модуль для генерации .mod-файлов для удалённого RTX-сервера.
Учитывает реальный путь модели на клиенте (/media/rtx-models/...)
и преобразует его в серверный (/srv/models/...).
"""

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class EnvConfig:
    last_scan_path: Path
    last_mods_path: Path
    llama_path: Optional[Path]
    ssh_host: Optional[str]
    default_config_path: Optional[Path]
    client_models_root: Path
    server_models_root: Path

def load_env(env_path: str | Path = ".env") -> EnvConfig:
    env_path = Path(env_path)
    if env_path.exists():
        load_dotenv(env_path)

    # Используем .absolute() вместо .resolve(), чтобы не "улетать" за пределы 
    # логической структуры из-за симлинков при проверке путей
    last_scan_path = Path(os.getenv("LAST_SCAN_PATH", "/media/rtx-models")).expanduser().absolute()
    last_mods_path = Path(os.getenv("LAST_MODS_PATH", "/home/yuri/MODS/")).expanduser().absolute()
    llama_path = os.getenv("LLAMA_PATH")
    ssh_host = os.getenv("SSH_HOST")
    default_config_path = os.getenv("DEFAULT_CONFIG_PATH")

    # Корни путей должны быть абсолютными для корректного сравнения
    client_models_root = Path("/media/rtx-models").absolute()
    server_models_root = Path("/srv/models").absolute()

    return EnvConfig(
        last_scan_path=last_scan_path,
        last_mods_path=last_mods_path,
        llama_path=Path(llama_path) if llama_path else None,
        ssh_host=ssh_host,
        default_config_path=Path(default_config_path) if default_config_path else None,
        client_models_root=client_models_root,
        server_models_root=server_models_root,
    )

@dataclass
class ModParams:
    threads: int = 4
    ctx: int = 32768
    batch: int = 320
    ngl: int = 60
    host: str = "0.0.0.0"
    port: int = 8080
    extra: str = ""

    def validate(self):
        """Проверка параметров перед сохранением."""
        if self.threads <= 0: raise ValueError("Threads must be > 0")
        if not (1 <= self.port <= 65535): raise ValueError("Invalid port range")
        if self.ctx < 8: raise ValueError("Context size too small")

def to_server_model_path(client_model_path: Path, cfg: EnvConfig) -> Path:
    """Преобразует клиентский путь в серверный."""
    # Используем absolute(), чтобы сохранить логическую структуру симлинков
    abs_client_path = client_model_path.expanduser().absolute()

    try:
        rel = abs_client_path.relative_to(cfg.client_models_root)
        return (cfg.server_models_root / rel).resolve() # Здесь resolve уместен для финального пути
    except ValueError:
        logger.warning(f"Path {abs_client_path} is not under client root {cfg.client_models_root}")
        return abs_client_path

def infer_model_name_from_path(model_path: Path) -> str:
    """Извлекает имя модели, корректно обрабатывая файлы в корне."""
    # Если путь — это файл прямо в корне моделей, берем его stem
    if model_path.parent == client_models_root_fallback(): # (см. рекомендации ниже)
        return model_path.stem

    parent = model_path.parent.name
    stem = model_path.stem

    # Список "технических" папок, которые не являются именами моделей
    ignored_dirs = {"_todo", "models", "gguf", "rtx-models"} 
    
    if parent and parent not in ignored_dirs:
        return parent
    return stem

def client_models_root_fallback():
    # Вспомогательная функция для логики в infer_model_name
    return Path("/media/rtx-models")

def build_mod_content(server_model_path: Path, params: ModParams) -> str:
    """Формирует содержимое .mod файла."""
    return (
        f'MODEL="{str(server_model_path)}"\n'
        f'HOST="{params.host}"\n'
        f'PORT="{params.port}"\n\n'
        f'THREADS="{params.threads}"\n\n'
        f'CTX="{params.ctx}"\n'
        f'BATCH="{params.batch}"\n'
        f'NGL="{params.ngl}"\n\n'
        f'EXTRA="{params.extra}"\n'
    )

def save_mod_file(content: str, cfg: EnvConfig, model_name: str, suffix: Optional[str] = None) -> Path:
    mods_dir = cfg.last_mods_path.expanduser()
    mods_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{model_name}_{suffix}.mod" if suffix else f"{model_name}.mod"
    mod_path = mods_dir / filename
    
    try:
        mod_path.write_text(content, encoding="utf-8")
        return mod_path
    except OSError as e:
        logger.error(f"Failed to save file {mod_path}: {e}")
        raise

def generate_mod_for_client_model(
    client_model_path: str | Path,
    env_path: str | Path = ".env",
    params: Optional[ModParams] = None,
    suffix: Optional[str] = None,
) -> Path:
    cfg = load_env(env_path)
    if params is None:
        params = ModParams()
    else:
        params.validate()

    client_model_path = Path(client_model_path).absolute()
    server_model_path = to_server_model_path(client_model_path, cfg)
    
    # Исправленная логика получения имени
    if client_model_path.parent == cfg.client_models_root:
        model_name = client_model_path.stem
    else:
        model_name = infer_model_name_from_path(server_model_path)

    content = build_mod_content(server_model_path, params)
    return save_mod_file(content, cfg, model_name, suffix=suffix)

if __name__ == "__main__":
    # Тест
    try:
        example_client_path = "/media/rtx-models/NVIDIA-Nemotron-3-Nano-4B-Q8_0/model.gguf"
        mod_file = generate_mod_for_client_model(example_client_path)
        print(f"Успех! Создан файл: {mod_file}")
    except Exception as e:
        print(f"Ошибка при генерации: {e}")