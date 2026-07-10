#!/bin/bash
cd "$(dirname "$0")"

# 检查并安装依赖
if ! python3 -c "import PySide6" 2>/dev/null; then
    echo "正在安装依赖..."
    python3 -m pip install -r requirements.txt --quiet
fi

python3 -m app.main
