"""Fetch complete Astana chain branches via the official 2GIS Places API.

Requires your own API key from dev.2gis.com; keys are never written to output/logs.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ORGS = {
    "Coffee BOOM": "70000001019422485",
    "ONESHOTT COFFEE": "70000001050742732",
    "Master Coffee": "70000001018515910",
    "Global Coffee": "70000001051512888",
}
API = "https://catalog.api.2gis.com/3.0/items"


def fetch_chain(chain: str, org_id: str, key: str, city_id: str) -> list[dict]:
    rows = []
    page = 1
    while True:
        query = urlencode({
            "org_id": org_id, "city_id": city_id, "page": page, "page_size": 50,
            "fields": "items.point,items.adm_div,items.org", "key": key,
        })
        request = Request(f"{API}?{query}", headers={"User-Agent": "Yummy/1.0"})
        with urlopen(request, timeout=20) as response:  # noqa: S310 - fixed HTTPS origin
            payload = json.load(response)
        result = payload.get("result", {})
        items = result.get("items", [])
        for item in items:
            point = item.get("point") or {}
            rows.append({
                "chain": chain,
                "name": item.get("name", chain),
                "address": item.get("address_name") or item.get("full_address_name") or "",
                "district": "",
                "lat": point.get("lat", ""), "lng": point.get("lon", ""),
                "source": "2GIS Places API", "source_id": item.get("id", ""),
                "source_url": f"https://2gis.kz/astana/firm/{item.get('id', '')}",
            })
        if not items or len(rows) >= int(result.get("total", len(rows))):
            break
        page += 1
    return rows


def main() -> int:
    key = os.getenv("DGIS_API_KEY", "")
    city_id = os.getenv("DGIS_CITY_ID", "")
    if not key or not city_id:
        print("Set DGIS_API_KEY and DGIS_CITY_ID (do not commit them)", file=sys.stderr)
        return 2
    rows = []
    for chain, org_id in ORGS.items():
        chain_rows = fetch_chain(chain, org_id, key, city_id)
        print(f"{chain}: {len(chain_rows)}")
        rows.extend(chain_rows)
    rows.sort(key=lambda row: (row["chain"], row["address"]))
    root = Path(__file__).resolve().parent.parent
    csv_path = root / "data/leads/astana_additional_chains_full.csv"
    json_path = root / "data/leads/astana_additional_chains_full.json"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(f"Saved {len(rows)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
