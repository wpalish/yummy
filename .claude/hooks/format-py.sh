#!/usr/bin/env bash
# PostToolUse-хук: после правки .py — проверить синтаксис, отформатировать если есть тулза.
# Самоохранный: молчит, если ruff/black не установлены. py_compile есть всегда.
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

# формат — только если тулза доступна (иначе тихо пропускаем)
if command -v ruff >/dev/null 2>&1; then ruff format "$FILE" >/dev/null 2>&1 || true; fi
if command -v black >/dev/null 2>&1; then black -q "$FILE" >/dev/null 2>&1 || true; fi
exit 0
