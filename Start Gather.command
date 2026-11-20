#!/bin/zsh
cd -- "${0:A:h}"
task_python="$PWD/.venv/bin/python"
if [[ ! -x "$task_python" ]]; then
  task_python="$(command -v python3)"
fi
if ! "$task_python" -c 'import fastapi,langgraph,fastmcp' 2>/dev/null; then
  print 'Install Python 3.12+, then run these commands in this folder:'
  print 'python3 -m venv .venv'
  print '.venv/bin/python -m pip install -r requirements-semantic.txt'
  read 'task_ack?Press Enter to close.'
  exit 1
fi
(
  sleep 2
  open 'http://127.0.0.1:8765'
) &
"$task_python" start.py
read 'task_ack?Press Enter to close.'
