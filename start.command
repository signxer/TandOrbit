#!/bin/bash
set -e
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
    if command -v python3.12 >/dev/null; then
        python3.12 -m venv .venv
    else
        python3 -c 'import sys; assert sys.version_info >= (3, 11), "需要 Python 3.11+"'
        python3 -m venv .venv
    fi
    .venv/bin/python -m pip install -e .
fi
exec .venv/bin/python -m app.main
