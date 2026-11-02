import requests, pathlib, re, json
out = []
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
B = "https://api.indec.gob.ar"
html = requests.get(B + "/datasets", headers=H, timeout=60).text
scripts = sorted(set(re.findall(r'src="([^"]+\.js[^"]*)"', html)))
out.append("SCRIPTS " + str(scripts))
urls = set()
for s in scripts:
    u = s if s.startswith("http") else B + ("" if s.startswith("/") else "/") + s
    try:
        js = requests.get(u, headers=H, timeout=60).text
    except Exception as e:
        out.append(f"ERR {u} {e}"); continue
    for m in re.findall(r'["\'`](/[a-zA-Z0-9_\-/{}.:?=&]*(?:api|v1|v2|dataset|series|openapi|swagger|docs)[a-zA-Z0-9_\-/{}.:?=&]*)["\'`]', js):
        urls.add(m)
    for m in re.findall(r'https?://[a-zA-Z0-9_\-.]*indec[a-zA-Z0-9_\-./{}?=&]*', js):
        urls.add(m)
out.append("RUTAS " + "\n ".join(sorted(urls)[:200]))
for path in ["/openapi.json", "/api/openapi.json", "/swagger.json", "/api/docs", "/api", "/api/v1", "/api/datasets", "/api/v1/datasets", "/v1/datasets", "/datasets.json", "/api/catalogo", "/docs/openapi.json"]:
    try:
        r = requests.get(B + path, headers=H, timeout=30)
        out.append(f"GET {path} {r.status_code} {r.headers.get('content-type')} {r.text[:300]!r}")
    except Exception as e:
        out.append(f"GET {path} ERR {e}")
pathlib.Path("data/sondeo_recaudacion.txt").write_text("\n".join(out)); print("\n".join(out))
