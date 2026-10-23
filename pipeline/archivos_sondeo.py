"""Exploración: baja archivos candidatos (Excel/CSV) y páginas índice para ver su estructura.

Para cada URL anota el código HTTP y el tamaño; los archivos que bajan bien se guardan en
data/archivos/ y, si son planillas, se resume cada hoja (primeras filas) en un .txt.
De las páginas HTML se extraen los enlaces a .xls/.xlsx/.csv.
"""
from __future__ import annotations

import io
import json
import re
import traceback
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "data" / "archivos"
CAB = {"User-Agent": "Mozilla/5.0 (datos-argentina; github.com/francomartinlopez/datosargentina)"}


def variantes_indec(patron: str, meses_atras: int = 14) -> list[str]:
    """Genera URLs con {MM}_{AA} para los últimos meses (INDEC nombra por mes de publicación)."""
    hoy = pd.Timestamp(date.today()).replace(day=1)
    out = []
    for k in range(meses_atras):
        f = hoy - pd.DateOffset(months=k)
        out.append(patron.format(MM=f"{f.month:02d}", AA=f"{f.year % 100:02d}", AAAA=f.year))
    return out


ARCHIVOS = {
    "pobreza": variantes_indec("https://www.indec.gob.ar/ftp/cuadros/sociedad/cuadros_informe_pobreza_{MM}_{AA}.xls"),
    "oferta_demanda": variantes_indec("https://www.indec.gob.ar/ftp/cuadros/economia/sh_oferta_demanda_{MM}_{AA}.xls"),
    "balanza_pagos": variantes_indec("https://www.indec.gob.ar/ftp/cuadros/economia/sh_balanza_pagos_{MM}_{AA}.xls")
                      + variantes_indec("https://www.indec.gob.ar/ftp/cuadros/economia/sh_bal_pagos_{MM}_{AA}.xls"),
    "canastas": ["https://www.indec.gob.ar/ftp/cuadros/sociedad/serie_cba_cbt.xls"],
    "supermercados_prov": ["https://www.indec.gob.ar/ftp/cuadros/economia/serie_supermercados.xlsx",
                           "https://www.indec.gob.ar/ftp/cuadros/economia/serie_supermercados.xls"],
    "patentamientos_autos": ["https://estadisticas.produccion.gob.ar/app/dataset/6/distribution/6.3/autom-paten-series.csv"],
    "patentamientos_motos": ["https://estadisticas.produccion.gob.ar/app/dataset/14/distribution/14.1/motos-paten-series.csv"],
    "escrituras": ["https://estadisticas.produccion.gob.ar/app/dataset/7/distribution/7.1/escritura-canti-series.csv"],
    "bovinos": ["https://datos.magyp.gob.ar/dataset/9e3a2b3d-8b9c-4c71-9e5a-1f0e0b1c2a3d/resource/serie-tiempo-indicadores-mensuales-bovinos.csv"],
    "itcrm": ["https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/ITCRMSerie.xlsx"],
}
PAGINAS = {
    "deuda": "https://www.argentina.gob.ar/economia/finanzas/datos-trimestrales-de-la-deuda",
    "indec_pobreza": "https://www.indec.gob.ar/indec/web/Nivel4-Tema-4-46-152",
    "indec_bdp": "https://www.indec.gob.ar/indec/web/Nivel4-Tema-3-35-45",
    "indec_pib": "https://www.indec.gob.ar/indec/web/Nivel4-Tema-3-9-47",
    "trabajo_registrado": "https://www.argentina.gob.ar/trabajo/estadisticas/situacion-y-evolucion-del-trabajo-registrado",
    "coparticipacion": "https://www.economia.gob.ar/dnap/transferencias.html",
    "magyp_bovinos": "https://datos.magyp.gob.ar/dataset/indicadores-mensuales-bovinos",
    "energia_produccion": "http://datos.energia.gob.ar/dataset/produccion-de-petroleo-y-gas-por-pozo",
}


def resumir_planilla(contenido: bytes, nombre: str) -> str:
    partes = []
    try:
        hojas = pd.read_excel(io.BytesIO(contenido), sheet_name=None, header=None)
    except Exception as e:
        return f"No se pudo leer como planilla: {e!r}"
    for hoja, df in hojas.items():
        partes.append(f"=== Hoja: {hoja} ({df.shape[0]} filas x {df.shape[1]} columnas)")
        partes.append(df.head(30).iloc[:, :14].to_string(max_colwidth=28))
        partes.append("... últimas filas:")
        partes.append(df.tail(6).iloc[:, :14].to_string(max_colwidth=28))
    return "\n".join(partes)


def main() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    informe = {}
    for clave, urls in ARCHIVOS.items():
        informe[clave] = []
        for u in urls:
            try:
                r = requests.get(u, headers=CAB, timeout=60)
                informe[clave].append({"url": u, "status": r.status_code, "bytes": len(r.content), "tipo": r.headers.get("content-type")})
                if r.status_code == 200 and len(r.content) > 500 and "html" not in (r.headers.get("content-type") or ""):
                    ext = u.rsplit(".", 1)[-1]
                    (SALIDA / f"{clave}.{ext}").write_bytes(r.content)
                    if ext in ("xls", "xlsx"):
                        (SALIDA / f"{clave}.txt").write_text(resumir_planilla(r.content, clave), encoding="utf-8")
                    else:
                        (SALIDA / f"{clave}.txt").write_text(r.content[:6000].decode("utf-8", "replace"), encoding="utf-8")
                    break
            except Exception as e:
                informe[clave].append({"url": u, "error": repr(e)})
    enlaces = {}
    for clave, u in PAGINAS.items():
        try:
            r = requests.get(u, headers=CAB, timeout=60)
            links = sorted(set(urljoin(u, h) for h in re.findall(r'href="([^"]+\.(?:xlsx?|csv|zip))"', r.text, flags=re.I)))
            enlaces[clave] = {"status": r.status_code, "enlaces": links[:80]}
        except Exception as e:
            enlaces[clave] = {"error": repr(e)}
    (SALIDA / "informe.json").write_text(json.dumps({"archivos": informe, "paginas": enlaces}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        SALIDA.mkdir(parents=True, exist_ok=True)
        (SALIDA / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        print(traceback.format_exc())
