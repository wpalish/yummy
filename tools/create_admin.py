"""Безопасный bootstrap администратора Yummy (идея из Arena-ревью, PR #6).

Запуск локально или в Render Shell:
    python tools/create_admin.py owner@example.com

Пароль читается через getpass — не попадает в shell history / process list
(в отличие от передачи аргументом). Существующему аккаунту роль повышается
до admin с отзывом всех активных сессий (token_ver+1 — старые JWT умирают).

Дополняет YUMMY_ADMIN_EMAILS: env-способ работает при регистрации, этот —
для уже существующих аккаунтов и для сред, где env менять дольше, чем зайти
в Shell.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

# при запуске `python tools/create_admin.py` корень репо не в sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.accounts import RegisterInput, accounts, hash_password  # noqa: E402


def create_or_promote_admin(email: str, password: str | None) -> str:
    email = email.strip().lower()
    row = accounts.by_email(email)
    if row:
        with accounts._lock, accounts._conn() as c:  # noqa: SLF001 — CLI-инструмент того же пакета
            c.execute(
                "UPDATE users SET role='admin', token_ver=COALESCE(token_ver,0)+1 WHERE id=?",
                (row["id"],))
        return "promoted"
    if not password:
        raise SystemExit("аккаунта нет — для создания нового администратора нужен пароль")
    # переиспользуем единую password policy, не дублируя правила в CLI
    RegisterInput(email=email, password=password, role="customer")
    accounts.create(email, hash_password(password), "admin", None, None)
    return "created"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("email", help="email администратора")
    args = ap.parse_args()

    row = accounts.by_email(args.email.strip().lower())
    password = None
    if not row:
        password = getpass.getpass("Пароль нового администратора (мин. 8, буквы+цифры): ")
        if password != getpass.getpass("Повторите пароль: "):
            print("Пароли не совпадают", file=sys.stderr)
            return 1

    result = create_or_promote_admin(args.email, password)
    if result == "promoted":
        print(f"{args.email}: роль повышена до admin, все старые сессии отозваны")
    else:
        print(f"{args.email}: администратор создан")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
