import requests, pathlib, json
out = []
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
B = "https://api.indec.gob.ar"
items, pagina = [], 1
r = requests.get(B + "/api/datasets", headers=H, timeout=60).json()
out.append("KEYS " + json.dumps({k: (v if not isinstance(v, (list, dict)) else type(v).__name__) for k, v in r["data"].items()}))
items = r["data"]["items"]
tot = r["data"].get("total") or r["data"].get("count")
for p in range(2, 30):
    if tot and len(items) >= tot: break
    rr = requests.get(B + "/api/datasets", params={"page": p}, headers=H, timeout=60).json()
    nuevos = rr["data"]["items"]
    if not nuevos or nuevos[0]["id"] in {i["id"] for i in items}: break
    items += nuevos
out.append(f"TOTAL {len(items)} (declarado {tot})")
out.append("EJEMPLO " + json.dumps(items[0], ensure_ascii=False)[:1500])
for i in items:
    out.append(f"- {i.get('id')} | {i.get('slug')} | {i.get('name')} | {i.get('area')} | {str(i.get('description'))[:160]} | " + " ".join(f"{k}={i[k]}" for k in i if k in ('frequency','periodicity','periodicidad','updated_at','last_update','format','endpoint','url')))
s = items[0]["slug"]
for path in [f"/v1/{s}?limit=3", f"/api/datasets/{s}", f"/api/datasets/{items[0]['id']}", "/v1/"]:
    try:
        rr = requests.get(B + path, headers=H, timeout=30)
        out.append(f"GET {path} {rr.status_code} {rr.text[:1200]!r}")
    except Exception as e:
        out.append(f"GET {path} ERR {e}")
pathlib.Path("data/sondeo_recaudacion.txt").write_text("\n".join(out)); print("\n".join(out))
