import requests, pathlib, json
out = []
for i in ["186.3_JUBILACIONLES_0_0_49", "186.3_JUBILACIONINO_0_0_53"]:
    r = requests.get("https://apis.datos.gob.ar/series/api/series/", params={"ids": i, "format": "json", "limit": 5, "metadata": "full"}, timeout=60)
    j = r.json()
    out.append(f"{i} {r.status_code} count={j.get('count')} data={j.get('data')[:3] if j.get('data') else j.get('errors') or j}")
    m = (j.get("meta") or [{}, {}])
    if len(m) > 1: out.append(json.dumps(m[1].get("field"), ensure_ascii=False))
pathlib.Path("data/meta186.txt").write_text("\n".join(out)); print("\n".join(out))
