import os, requests, pathlib, json, collections
out = []
t = os.environ["INDEC_API_TOKEN"]
H = {"Authorization": f"Bearer {t}", "Prefer": "count=exact"}
B = "https://api.indec.gob.ar/v1/"
ds = ["comercio_exterior_exportacion_bienes", "comercio_exterior_importacion_bienes", "comercio_exterior_nomenclaturas",
      "proyecciones_poblacion_jurisdiccion_2022_2040", "estimaciones_poblacion_departamento_2022_2035",
      "ipc_nacional", "ipi_minero", "icc_precios_construccion", "canasta-crianza", "sipm_precios_mayoristas"]
for d in ds:
    try:
        r = requests.get(B + d, params={"limit": 2000}, headers=H, timeout=120)
        rows = r.json()
        out.append(f"\n=== {d} status={r.status_code} rango={r.headers.get('Content-Range')} cols={list(rows[0].keys()) if rows else None}")
        out.append("primera " + json.dumps(rows[0], ensure_ascii=False)[:500])
        for c in rows[0]:
            vals = collections.Counter(str(x.get(c)) for x in rows)
            if len(vals) <= 60 and c not in ("valor", "poblacion", "valor_FOB", "Peso_Neto", "valor_CIF"):
                out.append(f"  {c}: {len(vals)} -> " + " | ".join(f"{k}" for k, _ in vals.most_common(60))[:900])
            else:
                out.append(f"  {c}: {len(vals)} distintos, ej {list(vals)[:5]}")
    except Exception as e:
        out.append(f"=== {d} ERR {e}")
# últimos registros de las grandes
for d, orden in [("comercio_exterior_exportacion_bienes", "Periodo.desc"), ("ipc_nacional", "periodo.desc"), ("ipi_minero", "periodo.desc"), ("icc_precios_construccion", "periodo.desc"), ("canasta-crianza", "periodo.desc"), ("sipm_precios_mayoristas", "periodo.desc")]:
    try:
        r = requests.get(B + d, params={"limit": 3, "order": orden}, headers=H, timeout=60)
        out.append(f"ULT {d} {r.status_code} {r.text[:700]}")
    except Exception as e:
        out.append(f"ULT {d} ERR {e}")
pathlib.Path("data/sondeo_recaudacion.txt").write_text("\n".join(out)); print("\n".join(out))
