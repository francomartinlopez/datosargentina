import requests, pathlib, json
out = []
r = requests.get("https://apis.datos.gob.ar/series/api/search/", params={"dataset_id": "186", "limit": 100}, timeout=60)
try:
    for d in r.json().get("data", []):
        f = d.get("field", {}); ds = d.get("dataset", {})
        if str(f.get("id", "")).startswith("186.3"):
            out.append(f"{f.get('id')} | {f.get('description')} | {f.get('title')} | {ds.get('title')}")
except Exception as e:
    out.append(f"search err {e} {r.status_code} {r.text[:300]}")
r = requests.get("https://apis.datos.gob.ar/series/api/series/", params={"ids": "186.3_TOTAL_POLISOS_0_0_23,186.3_ASIGNACIONIAL_0_0_43", "metadata": "full", "last": 2}, timeout=60)
out.append(json.dumps(r.json().get("meta", ""), ensure_ascii=False)[:6000])
pathlib.Path("data/meta186.txt").write_text("\n".join(out))
print("\n".join(out))
