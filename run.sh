#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

export QT_LOGGING_RULES="*.warning=false"
export OPENCV_LOG_LEVEL=SILENT
export PYTHONWARNINGS="ignore"

if [ -f "./venv/bin/python3" ]; then
    PYTHONUNBUFFERED=1 ./venv/bin/python3 main.py "$@"
else
    PYTHONUNBUFFERED=1 python3 main.py "$@"
fi

