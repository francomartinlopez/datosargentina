import requests, pathlib, re, json
out = []
H = {"User-Agent": "Mozilla/5.0"}
r = requests.get("https://apis.datos.gob.ar/series/api/series/", params={"ids": "172.3_TL_RECAION_M_0_0_17", "metadata": "full", "last": 1}, timeout=60)
dist = r.json()["meta"][1]["distribution"]
out.append("DIST " + dist["title"] + " " + dist["downloadURL"])
t = requests.get(dist["downloadURL"], headers=H, timeout=60).text
lines = t.splitlines()
out.append("COLS " + lines[0])
out.append("LAST " + lines[-1])
out.append("FIRST " + lines[1])
for q in ["iva", "ganancias", "derechos de exportacion", "creditos y debitos", "seguridad social recaudacion"]:
    j = requests.get("https://apis.datos.gob.ar/series/api/search/", params={"q": q, "limit": 30}, timeout=60).json()
    for d in j.get("data", []):
        f = d["field"]
        if f["id"].startswith("172."):
            out.append(f"S {f['id']} | {f['title']} | {f.get('description')} | {f.get('time_index_end')}")
for u in ["https://www.argentina.gob.ar/economia/sechacienda/asuntosprovinciales/recaudacion",
          "https://www.argentina.gob.ar/economia/sechacienda/coordinacion-fiscal-provincial/recaudacion-provincial",
          "https://www.argentina.gob.ar/economia/sechacienda/coordinacion-fiscal-provincial",
          "https://www.argentina.gob.ar/economia/sechacienda/coordinacion-fiscal-provincial/recursos-tributarios-provinciales"]:
    try:
        p = requests.get(u, headers=H, timeout=60)
        links = sorted(set(re.findall(r'href="([^"]+\.(?:xlsx?|csv|zip))"', p.text)))
        sub = sorted(set(re.findall(r'href="(/economia/sechacienda/coordinacion-fiscal-provincial/[^"#?]+)"', p.text)))
        out.append(f"PAGE {u} {p.status_code} files={links[:40]} sub={sub[:40]}")
    except Exception as e:
        out.append(f"PAGE {u} ERR {e}")
pathlib.Path("data/sondeo_recaudacion.txt").write_text("\n".join(out)); print("\n".join(out))
