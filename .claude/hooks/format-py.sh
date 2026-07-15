#!/usr/bin/env bash
# PostToolUse-хук: после правки .py — синтакс-барьер (py_compile).
#
# Авто-форматирование НАМЕРЕННО отключено: у проекта компактный stdlib-стиль
# (плотные однострочники), а black переформатировал бы весь файл при правке
# одной строки и разнёс бы этот стиль (23 файла / ~1441 строка). ruff/black
# стоят в .venv для РУЧНОГО запуска и для skill /audit (`ruff check`), но не
# навязываются на каждый Edit. См. решение в git-истории этого файла.
set -euo pipefail

FILE="$(python3 -c 'import json,sys; print((json.load(sys.stdin).get("tool_input") or {}).get("file_path",""))' 2>/dev/null || true)"
[ -z "$FILE" ] && exit 0
case "$FILE" in
  *.py) ;;
  *) exit 0 ;;
esac
[ -f "$FILE" ] || exit 0

PY="${CLAUDE_PROJECT_DIR:-.}/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

# синтаксис — быстрый барьер против битых правок
"$PY" -m py_compile "$FILE" || { echo "[hook] SYNTAX ERROR: $FILE" >&2; exit 2; }
exit 0
