import requests, pathlib, re
out = []
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
pages = [
 "https://www.argentina.gob.ar/economia/ingresospublicos/recaudacion",
 "https://www.argentina.gob.ar/economia/ingresospublicos/recaudacion/series",
 "https://www.argentina.gob.ar/economia/ingresospublicos/recaudacion/series-de-tiempo",
 "https://www.argentina.gob.ar/economia/ingresospublicos",
 "https://www.afip.gob.ar/institucional/estudios/series-historicas/",
 "https://www.afip.gob.ar/institucional/estudios/",
 "https://www.arca.gob.ar/institucional/estudios/",
 "https://www.argentina.gob.ar/economia/sechacienda/coordinacion-fiscal-provincial/ejecucion-presupuestaria-provincial",
 "https://www.argentina.gob.ar/economia/sechacienda/coordinacion-fiscal-provincial/recursos-tributarios-provinciales",
 "https://www.argentina.gob.ar/economia/sechacienda/asuntosprovinciales",
 "https://www.argentina.gob.ar/economia/sechacienda/coordinacion-fiscal-provincial/informacion-fiscal-provincial",
]
for u in pages:
    try:
        p = requests.get(u, headers=H, timeout=60)
        links = sorted(set(re.findall(r'href="([^"]+\.(?:xlsx?|csv|zip))"', p.text, re.I)))
        sub = sorted(set(x for x in re.findall(r'href="(/economia/[^"#?]+|/institucional/estudios/[^"#?]+)"', p.text) if any(k in x for k in ["recaud", "serie", "tribut", "provincial", "estudios"])))
        out.append(f"PAGE {u} {p.status_code}\n  files={links[:60]}\n  sub={sub[:60]}")
    except Exception as e:
        out.append(f"PAGE {u} ERR {e}")
pathlib.Path("data/sondeo_recaudacion.txt").write_text("\n".join(out)); print("\n".join(out))
