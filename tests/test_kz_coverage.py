"""№15: непереведённая строка = красный тест, а не молчаливая RU/KZ-каша.

Полная замена системы локализации не оправдана (словарь+observer работает);
уязвимость была процессная — забыть перевод. Тест собирает статичные
UI-строки (заголовки/кнопки/лейблы/опции) из app/static/index.html и требует,
чтобы каждая была в словаре KZ, покрывалась KZ_RX или была в явном allowlist.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

HTML = (Path(__file__).parent.parent / "app" / "static" / "index.html").read_text(encoding="utf-8")

# Осознанно непереводимое: бренд, юр.документы (намеренно RU), техничные подписи
ALLOWLIST_EXACT = {
    "Yummy", "РУС", "ҚАЗ", "KZ", "…", "—", "·",
}
ALLOWLIST_SUBSTR = (
    "Публичная оферта", "Политика конфиденциальности", "Стандарты пищевой",
    "Договор с заведением",          # юр.документы — намеренно на русском
    "github.com", "@",               # ссылки/email
)


def _kz_keys() -> set[str]:
    m = re.search(r"const KZ=\{(.*?)\n\};", HTML, re.S)
    assert m, "словарь KZ не найден"
    return set(re.findall(r'"((?:[^"\\]|\\.)*)"\s*:', m.group(1)))


def _kz_rx() -> list[re.Pattern]:
    m = re.search(r"const KZ_RX=\[(.*?)\n\];", HTML, re.S)
    assert m, "KZ_RX не найден"
    out = []
    for js in re.findall(r"\[/(.+?)/([a-z]*),", m.group(1)):
        try:
            out.append(re.compile(js[0]))
        except re.error:
            pass
    return out


class _Collector(HTMLParser):
    """Текст интерактивных/заголовочных элементов вне <script>/<style>."""
    TAGS = {"h1", "h2", "h3", "h4", "button", "option", "label", "summary", "th"}

    def __init__(self):
        super().__init__()
        self.strings: set[str] = set()
        self._stack: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        self._stack.append(tag)

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        while self._stack and self._stack.pop() != tag:
            pass

    def handle_data(self, data):
        if self._skip or not self._stack or self._stack[-1] not in self.TAGS:
            return
        t = " ".join(data.split())
        # интересуют строки с кириллицей (латиница/цифры/эмодзи — не переводим)
        if len(t) >= 2 and re.search(r"[а-яА-ЯёЁ]", t):
            self.strings.add(t)


def test_static_ui_strings_have_kz_translation():
    c = _Collector()
    c.feed(HTML)
    keys = _kz_keys()
    rxs = _kz_rx()

    def covered(s: str) -> bool:
        if s in keys or s in ALLOWLIST_EXACT:
            return True
        if any(sub in s for sub in ALLOWLIST_SUBSTR):
            return True
        # точный ключ может быть на подстроку (kzText переводит trimmed-текст)
        if any(k and k in s for k in keys if len(k) >= len(s) - 2 and len(k) > 3):
            return True
        return any(r.fullmatch(s) for r in rxs)

    missing = sorted(s for s in c.strings if not covered(s))
    assert not missing, (
        f"{len(missing)} строк без KZ-перевода (добавьте в словарь KZ или allowlist):\n"
        + "\n".join(f"  - {s!r}" for s in missing[:40]))
