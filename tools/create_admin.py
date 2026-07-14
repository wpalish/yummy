"""Безопасный bootstrap администратора Yummy.

Запуск локально или в Render Shell:
    python tools/create_admin.py owner@example.com

Пароль читается через getpass и не попадает в shell history / process list.
Существующему аккаунту роль повышается с отзывом всех активных сессий.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

# При запуске ``python tools/create_admin.py`` корень репозитория не всегда в
# sys.path (в отличие от ``python -m``).
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.accounts import Accounts, RegisterInput, hash_password  # noqa: E402


def _validated_password(email: str, password: str) -> str:
    """Переиспользовать единую password policy, не дублируя правила в CLI."""
    RegisterInput(
        email=email,
        password=password,
        role="customer",
        accepted_terms=True,
    )
    return password


def create_or_promote_admin(accounts: Accounts, email: str, password: str | None) -> str:
    email = email.strip().lower()
    row = accounts.by_email(email)
    if row:
        accounts.set_role(row["id"], "admin")
        return "promoted"
    if password is None:
        raise ValueError("для нового администратора нужен пароль")
    _validated_password(email, password)
    accounts.create(
        email,
        hash_password(password),
        "admin",
        accepted_terms=True,
    )
    return "created"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Создать или повысить администратора Yummy")
    parser.add_argument("email", help="email администратора")
    parser.add_argument("--reset-mfa", action="store_true",
                        help="перевыпустить TOTP secret и recovery codes")
    args = parser.parse_args(argv)

    accounts = Accounts()
    existing = accounts.by_email(args.email.strip().lower())
    password: str | None = None
    if not existing:
        password = getpass.getpass("Новый пароль: ")
        confirmation = getpass.getpass("Повтори пароль: ")
        if password != confirmation:
            print("Пароли не совпадают", file=sys.stderr)
            return 2
    try:
        result = create_or_promote_admin(accounts, args.email, password)
    except ValueError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2
    email = args.email.strip().lower()
    row = accounts.by_email(email)
    action = "создан" if result == "created" else "повышен до admin"
    print(f"Администратор {email} {action}; прежние сессии отозваны.")
    if args.reset_mfa or not row["mfa_enabled"]:
        setup = accounts.configure_mfa(row["id"], email)
        print("\nДобавь TOTP в password manager/authenticator:")
        print(setup["uri"])
        print(f"Secret (показывается один раз): {setup['secret']}")
        print("Recovery codes (сохрани офлайн; каждый одноразовый):")
        for code in setup["recovery_codes"]:
            print(f"  {code}")
    else:
        print("MFA уже настроена. Для ротации: --reset-mfa")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
