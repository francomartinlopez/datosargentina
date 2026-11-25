"""Exploración: archivos oficiales de minería (SIACAM) y de estadísticas provinciales.

- SIACAM (Secretaría de Minería, mecon.gob.ar/dataset): columnas, primeras y últimas filas.
- Institutos de estadística de Santa Fe (IPEC), Córdoba (DGEyC), CABA (IDECBA) y provincia de
  Buenos Aires (DPE): planillas publicadas (búsqueda en la biblioteca de medios de WordPress y
  enlaces de la portada).

Salida en data/sondeo_regional.txt (rama "exploracion").
"""
from __future__ import annotations

import io
import re
import traceback
from pathlib import Path

import pandas as pd
import requests

from .fuentes import CABECERAS

SALIDA = Path(__file__).resolve().parents[1] / "data" / "sondeo_regional.txt"
MECON = "https://www.mecon.gob.ar/dataset/"
SIACAM = ["Comercio/expominerales-siacam.csv", "Comercio/expo-mineria-por-provincia.csv", "Comercio/expo-mineria-por-sector.csv",
          "Comercio/principales-productos-mineros-exportados.csv", "Tablero-Litio/Exportaciones-litio.csv",
          "ipi-minero/ipi-minero-series.csv", "ipi-minero/ipi-minero-produccion-litio.csv", "ipi-minero/ipi-minero-ramas-actividad.csv",
          "Empleo-rubro-prov.csv", "Cartera-de-Proyectos-Mineros-Metaliferos-y-Litio-del-SIACAM.xlsx",
          "VBP-VAP-Mineria.csv"]
SITIOS = {
    "santa_fe": "https://www.estadisticasantafe.gob.ar",
    "cordoba": "https://estadistica.cba.gov.ar",
    "caba": "https://www.estadisticaciudad.gob.ar/eyc",
    "pba": "https://www.estadistica.ec.gba.gov.ar",
}
TERMINOS = ["IPC", "precios", "empleo", "EPH", "exporta", "puerto", "actividad", "PBG", "salario", "desocup", "series"]
EXT = (".xlsx", ".xls", ".csv", ".ods", ".zip")


def get(url: str, **kw) -> requests.Response:
    return requests.get(url, headers=CABECERAS, timeout=(10, 40), **kw)


def mostrar_tabla(p, nombre: str, contenido: bytes) -> None:
    if nombre.endswith(".xlsx") or nombre.endswith(".xls"):
        hojas = pd.read_excel(io.BytesIO(contenido), sheet_name=None, header=None)
        for h, df in list(hojas.items())[:6]:
            p(f"  hoja {h!r}: {df.shape}")
            p(df.head(12).to_string(max_colwidth=40)[:3000])
            p(df.tail(4).to_string(max_colwidth=40)[:1200])
        return
    for enc in ("utf-8", "latin-1"):
        for sep in (",", ";"):
            try:
                df = pd.read_csv(io.BytesIO(contenido), sep=sep, encoding=enc)
                if df.shape[1] > 1:
                    p(f"  {df.shape} sep={sep!r} enc={enc}")
                    p("  columnas: " + str(list(df.columns))[:800])
                    p(df.head(8).to_string(max_colwidth=40)[:2500])
                    p(df.tail(8).to_string(max_colwidth=40)[:2500])
                    for c in df.columns[:6]:
                        if df[c].dtype == object and df[c].nunique() < 80:
                            p(f"  valores de {c}: {sorted(map(str, df[c].unique()))[:80]}")
                    return
            except Exception:
                continue
    p("  no se pudo leer: " + contenido[:300].decode("latin-1"))


def main() -> None:
    lineas: list[str] = []
    p = lineas.append
    try:
        from .fuentes.indec_api import consultar
        for c in ("mercado_trabajo_eph", "pobreza_eph"):
            filas = consultar(c, select="area_geografica_nom,desde:periodo.min(),hasta:periodo.max()", order="area_geografica_nom.asc")
            p(f"===== {c}: " + "; ".join(f"{f['area_geografica_nom']} ({f['desde']}-{f['hasta']})" for f in filas))
    except Exception:
        p(traceback.format_exc()[-400:])
    guardar(lineas)
    for ruta in SIACAM:
        p(f"\n===== SIACAM {ruta}")
        try:
            r = get(MECON + ruta)
            p(f"  HTTP {r.status_code}, {len(r.content)} bytes")
            if r.status_code == 200:
                mostrar_tabla(p, ruta.lower(), r.content)
        except Exception:
            p(traceback.format_exc()[-400:])
        guardar(lineas)

    for clave, base in SITIOS.items():
        p(f"\n===== {clave} {base}")
        vistos: dict[str, str] = {}
        for t in TERMINOS:
            try:
                r = get(f"{base}/wp-json/wp/v2/media", params={"search": t, "per_page": 100, "_fields": "source_url,date"})
                if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json"):
                    for m in r.json():
                        u = m.get("source_url", "")
                        if u.lower().endswith(EXT):
                            vistos[u] = m.get("date", "")[:10]
                else:
                    p(f"  media {t}: HTTP {r.status_code}")
                    break
            except Exception as e:
                p(f"  media {t}: {str(e)[:120]}")
                break
        try:
            r = get(base + "/")
            for u in re.findall(r'href="([^"]+)"', r.text):
                if u.lower().endswith(EXT) or any(k in u.lower() for k in ("precio", "ipc", "empleo", "export", "trabajo", "estadistica")):
                    vistos.setdefault(u, "portada")
        except Exception as e:
            p(f"  portada: {str(e)[:120]}")
        for u, f in sorted(vistos.items(), key=lambda x: x[1], reverse=True)[:150]:
            p(f"  {f} {u}")
        guardar(lineas)

    guardar(lineas)
    print("\n".join(lineas)[:3000])


def guardar(lineas: list[str]) -> None:
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text("\n".join(lineas), encoding="utf-8")


if __name__ == "__main__":
    main()
