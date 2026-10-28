import requests, pathlib
out = []
for q in ["jubilaciones pensiones sistema integrado previsional", "jubilaciones otros regimenes nacionales", "politica de ingresos"]:
    r = requests.get("https://apis.datos.gob.ar/series/api/search/", params={"q": q, "limit": 50}, timeout=60)
    for d in r.json().get("data", []):
        f = d.get("field", {})
        if str(f.get("id", "")).startswith("186.3"):
            out.append(f"{f.get('id')} | {f.get('title')} | {f.get('description')}")
out = sorted(set(out))
pathlib.Path("data/meta186.txt").write_text("\n".join(out) or "nada"); print("\n".join(out))
