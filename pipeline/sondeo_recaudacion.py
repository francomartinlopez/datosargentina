import os, requests, pathlib, json
out = []
t = os.environ.get("INDEC_API_TOKEN", "")
out.append(f"TOKEN presente={bool(t)} largo={len(t)}")
if t:
    for path in ["/v1/ipi_minero?limit=2", "/v1/proyecciones_poblacion_jurisdiccion_2022_2040?limit=2", "/v1/comercio_exterior_exportacion_bienes?limit=2"]:
        r = requests.get("https://api.indec.gob.ar" + path, headers={"Authorization": f"Bearer {t}"}, timeout=60)
        out.append(f"GET {path} {r.status_code} {r.text[:600]}")
pathlib.Path("data/sondeo_recaudacion.txt").write_text("\n".join(out)); print("\n".join(out))
