#!/usr/bin/env python3
"""PreToolUse-хук: блокирует заведомо опасные Bash-команды.

Детерминистический guard (не зависит от интерпретации модели). Читает JSON
события Claude Code со stdin, exit 2 = блокировка с сообщением в stderr.
Использует stdlib — работает без jq.
"""
import json
import re
import sys

DANGER = re.compile(
    r"""(
        rm\s+-rf\s+/(?:\s|$)          # rm -rf /
      | rm\s+-rf\s+~                   # rm -rf ~
      | :\(\)\s*\{\s*:\|:              # fork bomb
      | \bmkfs\b                       # форматирование ФС
      | \bdd\s+if=.*of=/dev/           # запись в устройство
      | \bsudo\s+rm\b
      | DROP\s+(TABLE|DATABASE)\b      # деструктив SQL
      | git\s+push\b[^\n]*--force[^\n]*\b(main|master)\b
      | \bshutdown\b | \breboot\b
      | curl\b[^|\n]*\|\s*(bash|sh)\b  # curl | bash
      | wget\b[^|\n]*\|\s*(bash|sh)\b
    )""",
    re.IGNORECASE | re.VERBOSE,
)


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0  # не мешаем, если вход не распарсился
    cmd = (data.get("tool_input") or {}).get("command", "") or ""
    if DANGER.search(cmd):
        print(f"BLOCKED opasnaya komanda: {cmd}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
