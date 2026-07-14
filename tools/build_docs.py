"""Воспроизводимая сборка изолированной GitHub Pages демки (docs/).

Production работает same-origin через backend и HttpOnly cookies. Pages намеренно
остаётся browser-only демо: подключать её cross-origin к живому API запрещено,
иначе пришлось бы ослабить SameSite/CORS session boundary.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys

PAGES_API_BASE = os.getenv("YUMMY_PAGES_API_BASE", "").rstrip("/")
ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
DOCS = ROOT / "docs"

API_START = "const cookieValue=name=>"
API_END = 'const get=u=>api("GET",u), post=(u,b)=>api("POST",u,b);'
LEAFLET_TAG = ('<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" '
               'integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" '
               'crossorigin="anonymous"></script>')
QR_TAG = LEAFLET_TAG + '\n<script src="https://cdn.jsdelivr.net/npm/qrcode-generator@1.4.4/qrcode.js"></script>'


def load_client_store() -> str:
    return (STATIC / "demo-store.js").read_text(encoding="utf-8").rstrip()


def build_demo_js() -> str:
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    try:
        start = js.index(API_START)
        end = js.index(API_END, start) + len(API_END)
    except ValueError as exc:
        raise RuntimeError("api-блок не найден в app/static/app.js") from exc
    dispatcher = '''
/* GitHub Pages: изолированный browser-only store, без production API/cookies. */
const API_BASE = "";
const get=u=>_demoGet(u);
const post=(u,b)=>_demoPost(u,b);
const api=(m,u,b)=>m==="GET"?_demoGet(u):_demoPost(u,b);'''
    built = js[:start] + load_client_store() + dispatcher + js[end:]
    return (built.replace("/static/img/", "img/")
                 .replace("/static/venues.json", "venues.json")
                 .replace('register("/sw.js")', 'register("sw.js")'))


def main() -> int:
    if PAGES_API_BASE:
        print(
            "ОШИБКА: cross-origin live API для Pages отключён. "
            "Production frontend обслуживается backend same-origin.",
            file=sys.stderr,
        )
        return 2

    html = (STATIC / "index.html").read_text(encoding="utf-8")
    html = (html.replace("/static/img/", "img/")
                .replace("/static/app.css", "app.css")
                .replace("/static/app.js", "app.js")
                .replace("/manifest.json", "manifest.json")
                .replace("/static/venues.json", "venues.json"))
    html = html.replace(LEAFLET_TAG, QR_TAG)

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "index.html").write_text(html, encoding="utf-8")
    (DOCS / "app.js").write_text(build_demo_js(), encoding="utf-8")
    shutil.copy(STATIC / "app.css", DOCS / "app.css")
    shutil.copy(STATIC / "venues.json", DOCS / "venues.json")

    manifest = json.loads((STATIC / "manifest.json").read_text(encoding="utf-8"))
    manifest["start_url"] = manifest["scope"] = "./"
    for icon in manifest["icons"]:
        icon["src"] = icon["src"].replace("/static/", "")
    for shortcut in manifest["shortcuts"]:
        shortcut["url"] = "." + shortcut["url"]
        for icon in shortcut["icons"]:
            icon["src"] = icon["src"].replace("/static/", "")
    (DOCS / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    sw = (STATIC / "sw.js").read_text(encoding="utf-8")
    sw = (sw.replace('"/"', '"./"')
            .replace("/static/app.css", "app.css")
            .replace("/static/app.js", "app.js")
            .replace("/static/img/", "img/"))
    (DOCS / "sw.js").write_text(sw, encoding="utf-8")

    js = (DOCS / "app.js").read_text(encoding="utf-8")
    ok = "_demoGet" in js and 'const API_BASE = ""' in js and "/session/login" in js
    total = sum((DOCS / name).stat().st_size for name in ("index.html", "app.js", "app.css"))
    print(f"docs bundle: {total} байт | browser-only demo | сборка ок: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
