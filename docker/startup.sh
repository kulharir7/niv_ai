#!/bin/bash
# Niv AI - Backend/Worker startup wrapper
# Installs niv_ai + dependencies before starting the main process
set -e

APP_DIR="/home/frappe/frappe-bench/apps/niv_ai"

if [ -d "$APP_DIR" ]; then
    echo "[niv_ai] Installing dependencies..."
    /home/frappe/frappe-bench/env/bin/pip install --quiet openai tiktoken pytesseract pdfplumber python-docx Pillow pandas openpyxl 2>&1 | tail -1
    echo "[niv_ai] Installing app in editable mode..."
    /home/frappe/frappe-bench/env/bin/pip install --quiet -e "$APP_DIR" 2>&1 | tail -1
    echo "[niv_ai] Setup complete."
else
    echo "[niv_ai] App directory not found at $APP_DIR, skipping."
fi

# Execute the original command
exec "$@"
