#!/bin/bash
cd /home/yuri/projects/LLM-Cluster/LLM-Control-v2

echo "=== Проверка синтаксиса Python ==="
python3 -m py_compile services/ssh_setup.py && echo "✓ services/ssh_setup.py OK" || echo "✗ services/ssh_setup.py ERROR"
python3 -m py_compile main_ui.py && echo "✓ main_ui.py OK" || echo "✗ main_ui.py ERROR"
python3 -m py_compile server_widget.py && echo "✓ server_widget.py OK" || echo "✗ server_widget.py ERROR"
python3 -m py_compile services/system_monitor.py && echo "✓ services/system_monitor.py OK" || echo "✗ services/system_monitor.py ERROR"

echo ""
echo "=== Проверка импорта ssh_setup ==="
python3 -c "from services.ssh_setup import SSHSetupHelper; print('✓ Импорт успешен')" 2>&1 || echo "✗ Импорт не удался"
