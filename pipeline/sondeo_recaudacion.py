import os, requests, pathlib, json, collections, time
out = []
t = os.environ["INDEC_API_TOKEN"]
H = {"Authorization": f"Bearer {t}", "Prefer": "count=exact"}
B = "https://api.indec.gob.ar/v1/"
def get(d, **p):
    r = requests.get(B + d, params=p, headers=H, timeout=180)
    return r
def distintos(rows, cols):
    return {c: sorted(collections.Counter(str(x.get(c)) for x in rows).items(), key=lambda kv: -kv[1])[:80] for c in cols}
r = get("ipc_nacional", periodo="eq.202609", tipo_de_indicador="eq.Indice", limit=5000)
rows = r.json(); out.append(f"IPC 202609 indice n={len(rows)}")
for c, v in distintos(rows, ["region", "nivel", "clasificador"]).items(): out.append(f"  {c}: {v}")
gba = [x for x in rows if x["region"] == "GBA"]
out.append("  GBA items: " + " | ".join(f"{x['nivel'][:3]}:{x['codigo']}:{x['descripcion']}" for x in gba)[:6000])
out.append("  Nacional/otras regiones items: " + str(collections.Counter((x["region"], x["nivel"]) for x in rows)))
r = get("ipc_nacional", select="periodo", region="eq.Patagonia", codigo="eq.0", tipo_de_indicador="eq.Indice", order="periodo.asc", limit=3)
out.append("IPC patagonia nivel general primeras " + r.text[:300])
r = get("ipi_minero", periodo="eq.202608", limit=2000); rows = r.json()
out.append(f"IPI minero 202608 n={len(rows)}: " + " || ".join(f"{x['cuadro_web']}|{x['descripcion']}|{x['tipo_de_indicador']}|{x['unidad_de_medida']}|{x['serie']}|{round(x['valor'] or 0,1)}" for x in rows)[:5000])
r = get("sipm_precios_mayoristas", periodo="eq.202609", tipo_de_indicador="eq.Indice", limit=5000); rows = r.json()
out.append(f"SIPM 202609 n={len(rows)}: " + str(collections.Counter((x['indicador'], x['nivel'], x['clasificador']) for x in rows)))
out.append("  generales: " + " | ".join(f"{x['indicador']}:{x['codigo_apertura']}:{x['descripcion']}={x['valor']}" for x in rows if x['nivel'] in ('Nivel general',) or x['codigo_apertura'] in ('NG','0','N','T'))[:2000])
r = get("sipm_precios_mayoristas", select="indicador,periodo", tipo_de_indicador="eq.Indice", nivel="eq.Nivel general", order="periodo.asc", limit=20)
out.append("  SIPM nivel general primeras: " + r.text[:800])
r = get("icc_precios_construccion", select="periodo,valor,descripcion", codigo_apertura="eq.0", tipo_de_indicador="eq.Indice", order="periodo.asc", limit=3)
out.append("ICC primeras " + r.text[:400])
# agregados en exportaciones
for p in [dict(select="pais_cod,valor_FOB.sum()", Anio="eq.2025"), dict(select="pais_cod,total:valor_FOB.sum()", Anio="eq.2025")]:
    r = get("comercio_exterior_exportacion_bienes", **p, limit=5)
    out.append(f"AGG {p} {r.status_code} {r.text[:300]}")
t0 = time.time(); r = get("comercio_exterior_exportacion_bienes", Anio="eq.2025", limit=100000)
out.append(f"EXPO 2025 status={r.status_code} rango={r.headers.get('Content-Range')} n={len(r.json()) if r.ok else r.text[:200]} t={time.time()-t0:.1f}s")
r = get("comercio_exterior_nomenclaturas", limit=1000)
out.append("NOMEN " + json.dumps([[x['nombre_columna'], x['codigo'], x['codigo_descripcion']] for x in r.json() if x['nombre_columna'] != 'pais_cod'], ensure_ascii=False)[:4000])
paises = {x['codigo']: x['codigo_descripcion'] for x in r.json() if x['nombre_columna'] == 'pais_cod'}
out.append("PAISES " + json.dumps(paises, ensure_ascii=False)[:3000])
r = get("proyecciones_poblacion_jurisdiccion_2022_2040", select="fecha", order="fecha.desc", limit=1)
out.append("POB ult fecha " + r.text + " rango " + str(r.headers.get('Content-Range')))
r = get("proyecciones_poblacion_nacional_2022_2040", limit=3)
out.append("POBNAC " + str(r.headers.get('Content-Range')) + r.text[:500])
pathlib.Path("data/sondeo_recaudacion.txt").write_text("\n".join(out)); print("\n".join(out))
