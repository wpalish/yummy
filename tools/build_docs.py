"""Сборка статической версии Yummy для GitHub Pages (docs/).

Берёт app/static/index.html, заменяет серверный api-слой на клиентский стор
(localStorage) и чинит пути. Клиентский стор извлекается из предыдущей сборки
docs/index.html (единственный источник правды после утери scratchpad-копии).
"""
from __future__ import annotations

import os
import pathlib
import shutil
import sys

# Адрес задеплоенного бэкенда для витрины на Pages.
#   пусто          → демо-режим (данные в браузере, как сейчас)
#   https://…      → все запросы Pages идут в реальный сервер
# Задаётся: YUMMY_PAGES_API_BASE=https://yummy-astana.onrender.com make docs
PAGES_API_BASE = os.getenv("YUMMY_PAGES_API_BASE", "").rstrip("/")

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
DOCS = ROOT / "docs"

API_BLOCK = '''async function api(m,u,b,_retry,_net){const h=b?{"Content-Type":"application/json"}:{};
  const a=account(); if(a&&a.token)h["Authorization"]="Bearer "+a.token;
  let r;
  try{ r=await fetch(u,{method:m,headers:h,body:b?JSON.stringify(b):undefined}); }
  catch(err){                                      // сеть упала / сервер спит
    if(m==="GET"&&(_net||0)<3){ netBanner(true);   // GET безопасно ретраить
      await new Promise(s=>setTimeout(s,4000));
      return api(m,u,b,_retry,(_net||0)+1);
    }
    netBanner(false);
    throw new Error("Нет связи с сервером — попробуйте ещё раз через минуту");
  }
  netBanner(false);
  if(r.status===401&&!_retry&&a&&a.refresh&&!u.startsWith("/auth/")){
    try{const rr=await fetch("/auth/refresh",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({refresh_token:a.refresh})});
      if(rr.ok){const j=await rr.json();a.token=j.access_token;a.refresh=j.refresh_token;setAccount(a);return api(m,u,b,true);}}catch(e){}
  }
  if(!r.ok){let d;try{d=await r.json();}catch(e){} throw new Error((d&&d.detail)||("Ошибка "+r.status));} return r.status===204?null:r.json();}
const get=u=>api("GET",u), post=(u,b)=>api("POST",u,b), del=u=>api("DELETE",u);'''

LEAFLET_TAG = '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha384-cxOPjt7s7Iz04uaHJceBmS+qpjv2JkIHNVcuOrM+YHwZOmJGBXI00mdUXEq65HTH" crossorigin="anonymous"></script>'
QR_TAG = LEAFLET_TAG + '\n<script src="https://cdn.jsdelivr.net/npm/qrcode-generator@1.4.4/qrcode.js" integrity="sha384-8FWZA6BGMXhsfO+BLtrJK0We6gg5o1JyO8xQm6peWDEUs17ACA5ziE/NIAkl9z2k" crossorigin="anonymous"></script>'


def extract_client_store() -> str:
    """Достать client-store из прошлой сборки docs/index.html."""
    old = (DOCS / "index.html").read_text(encoding="utf-8")
    start = old.index("/* ===== CLIENT-SIDE STORE")
    # стоп ПЕРЕД диспетчером (если он уже вставлялся в прошлой сборке) — иначе
    # каждая пересборка дублировала бы API_BASE/api. Иначе — до STATUS_RU.
    marker = old.find("/* Переключатель бэкенда", start)
    end = marker if marker != -1 else old.index("const STATUS_RU=", start)
    return old[start:end].rstrip()


def main() -> int:
    client = extract_client_store()
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    html = (html.replace("/static/img/", "img/")
                .replace("/static/manifest.json", "manifest.json")
                .replace("/static/sw.js", "sw.js")
                .replace("/static/venues.json", "venues.json")
                # GitHub Pages не инжектит nonce и не шлёт CSP-заголовок — плейсхолдер
                # убираем, чтобы inline <script> остался валидным (без мёртвого nonce).
                .replace(' nonce="__CSP_NONCE__"', "")
                # Telegram-канал: handle из env запекаем в статику для Pages.
                .replace("__TG_CHANNEL__", os.getenv("YUMMY_TG_CHANNEL", ""))
                # Режим оплаты для Pages (demo — витрина-пилот, disabled — покупка выкл).
                .replace("__PAYMENT_MODE__", os.getenv("YUMMY_PAYMENT_MODE", "demo")))
    if API_BLOCK not in html:
        print("ОШИБКА: api-блок не найден в app/static/index.html", file=sys.stderr)
        return 1

    # client-store → внутренние _demoGet/_demoPost; поверх — диспетчер по API_BASE
    client = (client.replace("async function get(u){", "async function _demoGet(u){")
                    .replace("async function post(u,body){", "async function _demoPost(u,body){"))
    dispatcher = f'''
/* Переключатель бэкенда: пусто → демо (данные в браузере); URL → реальный сервер */
const API_BASE = "{PAGES_API_BASE}";
async function api(m,u,b,_retry,_net){{const h=b?{{"Content-Type":"application/json"}}:{{}};
  const a=account(); if(a&&a.token)h["Authorization"]="Bearer "+a.token;
  let r;
  try{{ r=await fetch(API_BASE+u,{{method:m,headers:h,body:b?JSON.stringify(b):undefined}}); }}
  catch(err){{
    if(m==="GET"&&(_net||0)<3){{ netBanner(true);
      await new Promise(s=>setTimeout(s,4000));
      return api(m,u,b,_retry,(_net||0)+1);
    }}
    netBanner(false);
    throw new Error("Нет связи с сервером — попробуйте ещё раз через минуту");
  }}
  netBanner(false);
  if(r.status===401&&!_retry&&a&&a.refresh&&!u.startsWith("/auth/")){{
    try{{const rr=await fetch(API_BASE+"/auth/refresh",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{refresh_token:a.refresh}})}});
      if(rr.ok){{const j=await rr.json();a.token=j.access_token;a.refresh=j.refresh_token;setAccount(a);return api(m,u,b,true);}}}}catch(e){{}}
  }}
  if(!r.ok){{let d;try{{d=await r.json();}}catch(e){{}} throw new Error((d&&d.detail)||("Ошибка "+r.status));}} return r.status===204?null:r.json();}}
const get=(u)=>API_BASE?api("GET",u):_demoGet(u);
const post=(u,b)=>API_BASE?api("POST",u,b):_demoPost(u,b);
const del=(u)=>API_BASE?api("DELETE",u):_demoDelete(u);'''
    html = html.replace(API_BLOCK, client + dispatcher)
    html = html.replace(LEAFLET_TAG, QR_TAG)
    (DOCS / "index.html").write_text(html, encoding="utf-8")

    for name in ("manifest.json", "sw.js", "venues.json"):
        src = STATIC / name
        if src.exists():
            shutil.copy(src, DOCS / name)

    # синхронизируем картинки (лого/favicon/боксы) — иначе docs/img/ дрейфует
    img_src = STATIC / "img"
    if img_src.is_dir():
        (DOCS / "img").mkdir(exist_ok=True)
        for f in img_src.iterdir():
            if f.is_file():
                shutil.copy(f, DOCS / "img" / f.name)

    ok = "_demoGet" in html and "const API_BASE" in html
    mode = f"бэкенд {PAGES_API_BASE}" if PAGES_API_BASE else "демо (данные в браузере)"
    print(f"docs/index.html: {len(html)} байт | режим: {mode} | сборка ок: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
