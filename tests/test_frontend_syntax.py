"""Синтакс-барьер фронта: инлайн-JS обеих страниц обязан парситься.

Урок 2026-07-19: дубль `const` молча убил ВЕСЬ сайт — SyntaxError валит весь
инлайн-скрипт, консоль пустая, каждая функция undefined. 166 бэкенд-тестов
этого не видят. Этот тест видит.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


def _inline_js(page: Path) -> str:
    """Самый большой инлайн-скрипт страницы (в docs/ nonce вырезан сборкой,
    поэтому матчим и <script nonce=…>, и голый <script>)."""
    lines = page.read_text(encoding="utf-8").split("\n")
    blocks: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if ("<script nonce=" in line or line.strip() == "<script>"):
            buf = [line.split(">", 1)[1] if ">" in line else ""]
            for j in range(i + 1, len(lines)):
                if "</script>" in lines[j]:
                    buf.append(lines[j].split("</script>")[0])
                    i = j
                    break
                buf.append(lines[j])
            blocks.append("\n".join(buf))
        i += 1
    assert blocks, f"{page}: инлайн-скрипт не найден"
    return max(blocks, key=len)


@pytest.mark.parametrize("page", ["app/static/index.html", "docs/index.html"])
def test_inline_js_parses(page, tmp_path):
    if not shutil.which("node"):
        pytest.skip("node не установлен")
    js = tmp_path / "app.js"
    js.write_text(_inline_js(ROOT / page), encoding="utf-8")
    r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
    assert r.returncode == 0, f"{page}: SyntaxError в инлайн-JS:\n{r.stderr[:1500]}"
