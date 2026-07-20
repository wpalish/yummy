"""Сборка app/static/index.html из модулей-исходников.

Монолит фронта распилен на:
  app/static/src/shell.html   — HTML+CSS + плейсхолдер @@JS_BUNDLE@@ в <script>
  app/static/src/js/*.js      — JS по фичам, конкатенируются В ПОРЯДКЕ ИМЁН

ВАЖНО: все модули склеиваются в ОДИН inline <script> — так сохраняется единая
лексическая область (top-level const/let видны между «модулями»), CSP-nonce и
per-request плейсхолдеры (__CSP_NONCE__/__TG_CHANNEL__/__PAYMENT_MODE__). Порядок
конкатенации = исходный порядок в файле → поведение побайтово неизменно.

index.html — генерируемый артефакт (как docs/index.html): править модули, потом
`make index`. Тест test_index_build стережёт, что коммит не разошёлся с исходниками.
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "app" / "static" / "src"
OUT = ROOT / "app" / "static" / "index.html"
MARKER = "@@JS_BUNDLE@@"


def render() -> str:
    shell = (SRC / "shell.html").read_text(encoding="utf-8")
    if MARKER not in shell:
        raise SystemExit(f"ОШИБКА: {MARKER} не найден в shell.html")
    modules = sorted((SRC / "js").glob("*.js"))
    if not modules:
        raise SystemExit("ОШИБКА: нет модулей в src/js/")

    def _body(m: pathlib.Path) -> str:
        # каждый модуль — точный срез строк исходника + ОДИН convention-\n при
        # записи. Отрезаем ровно этот один \n (не rstrip: пустые строки-разделители
        # на стыках секций значимы), тогда '\n'.join даёт исходный <script> побайтово
        t = m.read_text(encoding="utf-8")
        return t[:-1] if t.endswith("\n") else t

    bundle = "\n".join(_body(m) for m in modules)
    return shell.replace(MARKER, bundle)


def main() -> int:
    html = render()
    OUT.write_text(html, encoding="utf-8")
    print(f"app/static/index.html: {len(html)} байт | "
          f"{len(list((SRC / 'js').glob('*.js')))} модулей")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
