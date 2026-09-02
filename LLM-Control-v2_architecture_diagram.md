# Диаграммы архитектуры LLM-Control-v2

## 1. Общая архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                    LLM-Control v2 Desktop App               │
│                        PySide6 / Qt                         │
└─────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│                    MainWindow / Main UI                     │
│  - Координация вкладок                                      │
│  - Статус-бар с метриками                                   │
│  - Управление потоками                                      │
└─────────────────────────────────────────────────────────────┘
          │              │              │
          ▼              ▼              ▼
   ┌─────────┐    ┌─────────┐    ┌─────────┐
   │ Scanner │    │ Config  │    │ Server  │
   │ Widget  │    │ Widget  │    │ Widget  │
   └─────────┘    └─────────┘    └─────────┘
          │              │              │
          ▼              ▼              ▼
   ┌─────────────────────────────────────────────────────────┐
   │                    Services Layer                       │
   │  - model_scanner.py                                     │
   │  - mod_generator.py                                     │
   │  - system_monitor.py                                    │
   │  - server_control.py                                    │
   │  - ssh_setup.py                                         │
   └─────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Infrastructure Layer                     │
│  - SSH / Paramiko                                           │
│  - psutil / Process control                                 │
│  - File system                                              │
│  - Network / WoL                                            │
└─────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Remote RTX Server                        │
│  - llama-server instances                                   │
│  - GPU / VRAM                                               │
│  - SSH access                                               │
└─────────────────────────────────────────────────────────────┘
```

## 2. Поток сканирования

```
User → ScannerWidget → model_scanner.find_files_by_extension
                                      │
                                      ▼
                              File System
                                      │
                                      ▼
                         models_data list
                                      │
                                      ▼
                         MainWindow → ConfigWidget.set_model
```

## 3. Поток генерации конфига

```
ConfigWidget → EnvConfig.load_env
                     │
                     ▼
            to_server_model_path
                     │
                     ▼
            ModParams.validate
                     │
                     ▼
            build_mod_content
                     │
                     ▼
            save_mod_file → .mod file
```

## 4. Поток управления сервером

```
ServerWidget → ServerControl → SSH
                                      │
                                      ▼
                              llmctl commands
                                      │
                                      ▼
                         Remote RTX Server
```

## 5. Поток мониторинга

```
RemoteMonitorThread → SSH → Paramiko
                                      │
                                      ▼
                         Collect metrics
                                      │
                                      ▼
                         Signal metrics_received
                                      │
                                      ▼
                         MainWindow status bar
```

## 6. Зависимости компонентов

### MainWindow зависит от:
- ScannerWidget
- ConfigWidget
- ServerWidget
- RemoteMonitorThread
- ServerControl

### ConfigWidget зависит от:
- EnvConfig
- ModParams
- model_layers.json

### ServerWidget зависит от:
- SSHSetupHelper
- ServerControl
- RemoteMonitorThread

### Services зависят от:
- .env конфигурация
- SSH ключи
- Файловая система

## 7. Коммуникация между компонентами

### Сигналы Qt:
- `scan_started` — начало сканирования
- `scan_finished` — завершение сканирования
- `model_selected` — выбор модели
- `run_command_requested` — запрос команды на сервер
- `metrics_received` — новые метрики

### Прямые вызовы:
- MainWindow → ConfigWidget.set_model
- ConfigWidget → ServerWidget.set_config
- ScannerWidget → MainWindow → ConfigWidget

## 8. Конфигурационные потоки

```
.env → EnvConfig → ModParams → .mod file
  │
  ▼
Server config paths → SSH upload → Remote server
```

## 9. Потоки данных

### Клиент → Сервер:
- Путь модели: `/media/rtx-models/...` → `/srv/models/...`
- Конфиг: локальный `.mod` → удалённый `.conf`
- Команды: UI → SSH → `llmctl`

### Сервер → Клиент:
- Метрики: SSH → RemoteMonitorThread → UI
- Логи: SSH → ServerWidget → UI
- Статус: SSH → ServerControl → UI

## 10. Проблемы архитектуры

### Текущие проблемы:
1. Циклические зависимости между UI и сервисами
2. Отсутствие слоя абстракции для SSH
3. Смешение UI и бизнес-логики
4. Отсутствие DI контейнера
5. Хардкод путей

### Рекомендуемая архитектура:

```
┌─────────────────────────────────────────────────────────────┐
│                        Presentation Layer                   │
│  - Qt Widgets / UI                                          │
└─────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│                      Application Layer                      │
│  - Use Cases / Commands                                     │
│  - DTOs                                                     │
└─────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│                       Domain Layer                          │
│  - Entities                                                 │
│  - Value Objects                                            │
│  - Domain Services                                          │
└─────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│                    Infrastructure Layer                     │
│  - SSH Client                                               │
│  - File Repository                                          │
│  - Process Control                                          │
└─────────────────────────────────────────────────────────────┘
```

## 11. Последовательность вызовов

### Сканирование модели:
1. User нажимает "Сканировать"
2. ScannerWidget.start_scan
3. model_scanner.find_files_by_extension
4. Обработка результатов
5. Сигнал scan_finished
6. MainWindow обновляет UI

### Генерация конфига:
1. User выбирает модель
2. ConfigWidget.set_model
3. EnvConfig.load_env
4. to_server_model_path
5. build_mod_content
6. save_mod_file

### Управление сервером:
1. User нажимает "Старт"
2. ServerWidget.validate_config
3. SSH upload конфига
4. SSH exec llmctl start
5. Обновление статуса

## 12. Рекомендации по улучшению архитектуры

1. Внедрить Clean Architecture
2. Добавить слой Application Services
3. Выделить Domain Model
4. Добавить Repository Pattern
5. Внедрить Dependency Injection
6. Добавить Event Bus
7. Выделить Configuration Management
8. Добавить Logging и Monitoring

---

*Диаграммы созданы для внутреннего использования. Описывают текущую архитектуру и рекомендации по улучшению.*
</atem:def>
