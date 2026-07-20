"""index.html — генерируемый из app/static/src/ (монолит распилен на модули).

Этот тест стережёт, что закоммиченный index.html СОВПАДАЕТ со сборкой из
исходников: иначе кто-то правил сгенерированный файл руками, и правка потеряется
при следующем `make index`. Плюс проверяет, что модули склеиваются в ОДИН
<script> (единая лексическая область для top-level const/let).
"""
from __future__ import annotations

from pathlib import Path

from tools import build_index

ROOT = Path(__file__).parent.parent
INDEX = ROOT / "app" / "static" / "index.html"


def test_committed_index_matches_sources():
    built = build_index.render()
    committed = INDEX.read_text(encoding="utf-8")
    assert built == committed, (
        "app/static/index.html разошёлся с app/static/src/ — "
        "правьте модули и делайте `make index`, не сам index.html")


def test_single_inline_script():
    """Все модули — в одном <script>: cross-file top-level const иначе не виден."""
    html = INDEX.read_text(encoding="utf-8")
    assert html.count('<script nonce="__CSP_NONCE__">') == 1
    # плейсхолдеры per-request сохранены внутри бандла
    assert "__CSP_NONCE__" in html
    assert "__PAYMENT_MODE__" in html
