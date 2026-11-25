"""Exploración de la API del INDEC para minería y datos regionales.

Anota en data/sondeo_indec.txt:
- la lista de conjuntos que publica la API (raíz OpenAPI);
- las descripciones del IPI minero (índices y unidades físicas) con su primer y último período;
- columnas y una fila de muestra de exportaciones (para ver si hay NCM, provincia o aduana);
- conjuntos cuyo nombre sugiere datos provinciales o mineros, con columnas y una fila.
"""
from __future__ import annotations

import json
import traceback
from pathlib import Path

import requests

from .fuentes import CABECERAS, TIMEOUT
from .fuentes.indec_api import URL, consultar, token

SALIDA = Path(__file__).resolve().parents[1] / "data" / "sondeo_indec.txt"
CLAVES = ("provinc", "jurisdic", "region", "miner", "export", "opex", "aglomer", "eph", "empleo", "turismo", "construc")


def main() -> None:
    lineas: list[str] = []
    p = lineas.append
    cab = {**CABECERAS, "Authorization": f"Bearer {token()}"}
    try:
        raiz = requests.get(URL, headers=cab, timeout=TIMEOUT).json()
        conjuntos = sorted(k.strip("/") for k in raiz.get("paths", {}) if k.strip("/") and "{" not in k and "rpc" not in k)
        p(f"== {len(conjuntos)} conjuntos")
        p("\n".join(conjuntos))
    except Exception:
        conjuntos = []
        p("raíz: " + traceback.format_exc()[-400:])

    p("\n== ipi_minero: descripciones")
    try:
        filas = consultar("ipi_minero", select="tipo_de_indicador,descripcion,desde:periodo.min(),hasta:periodo.max(),n:valor.count()",
                          order="tipo_de_indicador.asc,descripcion.asc")
        for f in filas:
            p(json.dumps(f, ensure_ascii=False))
        una = consultar("ipi_minero", limit=1)
        p("fila: " + json.dumps(una[:1], ensure_ascii=False))
    except Exception:
        p(traceback.format_exc()[-600:])

    for c in conjuntos:
        if not any(k in c.lower() for k in CLAVES):
            continue
        p(f"\n== {c}")
        try:
            r = requests.get(URL + c, params={"limit": 2}, headers=cab, timeout=TIMEOUT)
            p(json.dumps(r.json()[:2], ensure_ascii=False)[:1500])
        except Exception:
            p(traceback.format_exc()[-300:])

    # aperturas de exportación útiles: capítulo/NCM y provincia o aduana si existen
    for campo in ("provincia_cod", "provincia", "aduana_cod", "aduana", "capitulo", "ncm_cap", "rubro_cod", "gran_rubro_cod"):
        try:
            filas = consultar("comercio_exterior_exportacion_bienes", select=f"{campo},v:valor_FOB.sum()", Anio="eq.2025", order=f"{campo}.asc")
            p(f"\n== exportaciones 2025 por {campo}: {len(filas)} grupos")
            p(json.dumps(filas[:80], ensure_ascii=False)[:3000])
        except Exception as e:
            p(f"\n== exportaciones por {campo}: {str(e)[:150]}")

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text("\n".join(lineas), encoding="utf-8")
    print("\n".join(lineas)[:5000])


if __name__ == "__main__":
    main()
