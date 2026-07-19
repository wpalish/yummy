"""Шифрование merchant-реквизитов в покое (at rest), только stdlib.

AES в stdlib нет, а тащить cryptography ради одного поля не хотим (проект
намеренно на stdlib: PBKDF2 вместо passlib, JWT руками). Используем честную
конструкцию из примитивов hashlib/hmac:

  - поток ключа: HMAC-SHA256(enc_key, nonce || counter) блоками — CTR-режим,
    где HMAC выступает PRF (стандартная конструкция, как в NIST SP 800-108);
  - шифртекст XOR-ится с потоком;
  - целостность: encrypt-then-MAC HMAC-SHA256(mac_key, nonce || ct).

Ключи выводятся из YUMMY_CRED_KEY (или, как фолбэк, из YUMMY_SECRET_KEY) через
HKDF-подобное разделение: разные метки для enc и mac. Ротация ключа: выставить
новый YUMMY_CRED_KEY, старый — в YUMMY_CRED_KEY_OLD; decrypt пробует оба,
а re-encrypt при следующем сохранении переводит запись на новый ключ.

Формат: "enc1:" + base64url(nonce[16] | ct | tag[32]). Строки без префикса
считаются легаси-плейнтекстом и возвращаются как есть (миграция на лету).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets

_PREFIX = "enc1:"
_NONCE_LEN = 16
_TAG_LEN = 32


def _master_keys() -> list[bytes]:
    """Актуальный ключ + (опционально) старый для ротации."""
    keys = []
    for env in ("YUMMY_CRED_KEY", "YUMMY_CRED_KEY_OLD"):
        v = os.getenv(env, "")
        if v:
            keys.append(hashlib.sha256(v.encode()).digest())
    # Деривация из общего секрета — всегда в хвосте списка: как ЕДИНСТВЕННЫЙ
    # ключ она допустима только в деве (прод требует YUMMY_CRED_KEY —
    # assert_prod_config), а как fallback даёт расшифровку легаси-записей,
    # созданных до введения отдельного ключа.
    base = os.getenv("YUMMY_SECRET_KEY", "dev-secret-not-for-prod")
    keys.append(hashlib.sha256(("cred:" + base).encode()).digest())
    return keys


def _subkeys(master: bytes) -> tuple[bytes, bytes]:
    enc = hmac.new(master, b"enc", hashlib.sha256).digest()
    mac = hmac.new(master, b"mac", hashlib.sha256).digest()
    return enc, mac


def _keystream(enc_key: bytes, nonce: bytes, n: int) -> bytes:
    out = b""
    counter = 0
    while len(out) < n:
        out += hmac.new(enc_key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        counter += 1
    return out[:n]


def encrypt(plaintext: str) -> str:
    """Зашифровать строку актуальным ключом."""
    if not plaintext:
        return plaintext
    enc_key, mac_key = _subkeys(_master_keys()[0])
    nonce = secrets.token_bytes(_NONCE_LEN)
    pt = plaintext.encode()
    ct = bytes(a ^ b for a, b in zip(pt, _keystream(enc_key, nonce, len(pt))))
    tag = hmac.new(mac_key, nonce + ct, hashlib.sha256).digest()
    return _PREFIX + base64.urlsafe_b64encode(nonce + ct + tag).decode()


def decrypt(stored: str) -> str:
    """Расшифровать; легаси-плейнтекст (без префикса) вернуть как есть.
    Пробует актуальный и старый ключ (ротация). Битый шифртекст → ValueError."""
    if not stored or not stored.startswith(_PREFIX):
        return stored
    blob = base64.urlsafe_b64decode(stored[len(_PREFIX):])
    if len(blob) < _NONCE_LEN + _TAG_LEN:
        raise ValueError("повреждённый шифртекст")
    nonce, ct, tag = (blob[:_NONCE_LEN], blob[_NONCE_LEN:-_TAG_LEN], blob[-_TAG_LEN:])
    for master in _master_keys():
        enc_key, mac_key = _subkeys(master)
        if hmac.compare_digest(tag, hmac.new(mac_key, nonce + ct, hashlib.sha256).digest()):
            return bytes(a ^ b for a, b in zip(ct, _keystream(enc_key, nonce, len(ct)))).decode()
    raise ValueError("шифртекст не расшифрован ни одним ключом (сменился YUMMY_CRED_KEY?)")


def is_encrypted(stored: str) -> bool:
    return bool(stored) and stored.startswith(_PREFIX)
