"""Сборка статической версии Yummy для GitHub Pages (docs/).

Берёт app/static/index.html, заменяет серверный api-слой на клиентский стор
(localStorage) и чинит пути. Клиентский стор извлекается из предыдущей сборки
docs/index.html (единственный источник правды после утери scratchpad-копии).
"""
from __future__ import annotations

import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
DOCS = ROOT / "docs"

API_BLOCK = '''async function api(m,u,b,_retry){const h=b?{"Content-Type":"application/json"}:{};
  const a=account(); if(a&&a.token)h["Authorization"]="Bearer "+a.token;
  const r=await fetch(u,{method:m,headers:h,body:b?JSON.stringify(b):undefined});
  if(r.status===401&&!_retry&&a&&a.refresh&&!u.startsWith("/auth/")){
    try{const rr=await fetch("/auth/refresh",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({refresh_token:a.refresh})});
      if(rr.ok){const j=await rr.json();a.token=j.access_token;a.refresh=j.refresh_token;setAccount(a);return api(m,u,b,true);}}catch(e){}
  }
  if(!r.ok){let d;try{d=await r.json();}catch(e){} throw new Error((d&&d.detail)||("Ошибка "+r.status));} return r.status===204?null:r.json();}
const get=u=>api("GET",u), post=(u,b)=>api("POST",u,b);'''

LEAFLET_TAG = '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>'
QR_TAG = LEAFLET_TAG + '\n<script src="https://cdn.jsdelivr.net/npm/qrcode-generator@1.4.4/qrcode.js"></script>'


def extract_client_store() -> str:
    """Достать client-store из прошлой сборки docs/index.html."""
    old = (DOCS / "index.html").read_text(encoding="utf-8")
    start = old.index("/* ===== CLIENT-SIDE STORE")
    end = old.index("const STATUS_RU=", start)
    return old[start:end].rstrip()


def main() -> int:
    client = extract_client_store()
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    html = (html.replace("/static/img/", "img/")
                .replace("/static/manifest.json", "manifest.json")
                .replace("/static/sw.js", "sw.js")
                .replace("/static/venues.json", "venues.json"))
    if API_BLOCK not in html:
        print("ОШИБКА: api-блок не найден в app/static/index.html", file=sys.stderr)
        return 1
    html = html.replace(API_BLOCK, client)
    html = html.replace(LEAFLET_TAG, QR_TAG)
    (DOCS / "index.html").write_text(html, encoding="utf-8")

    for name in ("manifest.json", "sw.js", "venues.json"):
        src = STATIC / name
        if src.exists():
            shutil.copy(src, DOCS / name)

    ok = "fetch(u,{method" not in html
    print(f"docs/index.html: {len(html)} байт | fetch убран: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
