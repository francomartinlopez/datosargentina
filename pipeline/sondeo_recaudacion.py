import os, requests, pathlib, json, collections
out = []
t = os.environ["INDEC_API_TOKEN"]
H = {"Authorization": f"Bearer {t}", "Prefer": "count=exact"}
B = "https://api.indec.gob.ar/v1/"
def get(d, **p):
    return requests.get(B + d, params=p, headers=H, timeout=180)
r = get("ipi_minero", periodo="eq.202608", tipo_de_indicador="neq.Índice", limit=1000).json()
out.append("IPI MINERO no-indice 202608:\n  " + "\n  ".join(f"{x['cuadro_web']}|{x['tipo_de_indicador']}|{x['descripcion']}|{x['unidad_de_medida']}|{x['valor']}" for x in r if x['cuadro_web'] not in ('Cuadro 3', 'Cuadro 4', 'Cuadro 5')))
r = get("ipi_minero", select="periodo", tipo_de_indicador="eq.Unidades físicas", descripcion="eq.Carbonato de litio", order="periodo.asc", limit=2)
out.append("litio desde " + r.text)
r = get("comercio_exterior_nomenclaturas", nombre_columna="eq.uso_economico_cod").json()
out.append("USOS " + json.dumps([[x['codigo'], x['codigo_descripcion']] for x in r], ensure_ascii=False))
r = get("comercio_exterior_nomenclaturas", nombre_columna="eq.subrubro_cod").json()
out.append("SUBRUBROS " + json.dumps([[x['codigo'], x['codigo_descripcion']] for x in r], ensure_ascii=False)[-1500:])
r = get("proyecciones_poblacion_jurisdiccion_2022_2040", select="sexo_cod,sexo_nom,edad_cod", fecha="eq.2026", jurisdiccion_cod="eq.14", limit=200).json()
out.append("POB sexos " + str(collections.Counter((x['sexo_cod'], x['sexo_nom']) for x in r)) + " edades " + str(sorted(set(x['edad_cod'] for x in r))))
r = get("proyecciones_poblacion_jurisdiccion_2022_2040", select="jurisdiccion_nom,fecha,total:poblacion.sum()", fecha="in.(2022,2026,2040)", limit=200)
out.append("POB agg " + str(r.status_code) + " " + r.text[:1500])
r = get("comercio_exterior_exportacion_bienes", select="Periodo,pais_cod,v:valor_FOB.sum()", Anio="gte.2003", limit=1)
out.append("EXPO agg count " + str(r.headers.get('Content-Range')) + r.text[:200])
r = get("comercio_exterior_exportacion_bienes", select="Periodo,v:valor_FOB.sum()", Anio="eq.2025", order="Periodo.asc", limit=20)
out.append("EXPO total 2025 por mes (comparar con INDEC) " + r.text[:900])
r = get("comercio_exterior_importacion_bienes", select="Periodo,v:valor_CIF.sum()", Anio="eq.2025", order="Periodo.asc", limit=20)
out.append("IMPO total 2025 por mes " + r.text[:900])
r = get("ipc_nacional", select="region,periodo,valor", codigo="eq.0", tipo_de_indicador="eq.Indice", periodo="eq.202609", limit=20)
out.append("IPC NG 202609 " + r.text)
r = get("ipc_nacional", select="region,codigo,descripcion", tipo_de_indicador="eq.Indice", periodo="eq.202609", region="eq.Nacional", limit=50)
out.append("IPC Nacional items " + r.text[:2500])
pathlib.Path("data/sondeo_recaudacion.txt").write_text("\n".join(out)); print("\n".join(out))
