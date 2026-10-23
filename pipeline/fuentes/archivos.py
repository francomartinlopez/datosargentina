"""Series que salen de planillas publicadas como archivos (INDEC, BCRA).

Cada serie del catálogo indica el lector y qué fila o columna tomar, por ejemplo:

    pobreza_personas: {fuente: archivo, lector: indec_pobreza, campo: "Pobreza/Personas"}
    pib_real:         {fuente: archivo, lector: indec_oferta_demanda, campo: "Producto Interno Bruto"}

INDEC nombra muchos archivos con el mes de publicación (cuadros_informe_pobreza_10_26.xls),
así que se prueban los últimos meses hasta encontrar uno válido. Cuando el archivo no existe,
el servidor de INDEC responde 200 con una página HTML: se descarta mirando la firma del archivo.
"""
from __future__ import annotations

import io
import re
from datetime import date
from functools import lru_cache

import pandas as pd
import requests

from . import CABECERAS, TIMEOUT

INDEC = "https://www.indec.gob.ar/ftp/cuadros/"
ARCHIVOS = {
    "pobreza": INDEC + "sociedad/cuadros_informe_pobreza_{MM}_{AA}.xls",
    "oferta_demanda": INDEC + "economia/sh_oferta_demanda_{MM}_{AA}.xls",
    "canastas": INDEC + "sociedad/serie_cba_cbt.xls",
    "supermercados": INDEC + "economia/serie_supermercados.xlsx",
    "itcrm": "https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/ITCRMSerie.xlsx",
}
FIRMAS = (b"\xd0\xcf\x11\xe0", b"PK\x03\x04")  # xls (OLE2) y xlsx (zip)


def candidatos(patron: str, meses_atras: int = 15) -> list[str]:
    if "{MM}" not in patron:
        return [patron]
    hoy = pd.Timestamp(date.today()).replace(day=1)
    return [patron.format(MM=f"{f.month:02d}", AA=f"{f.year % 100:02d}")
            for f in (hoy - pd.DateOffset(months=k) for k in range(meses_atras))]


@lru_cache(maxsize=None)
def bajar(clave: str) -> bytes:
    """Devuelve el archivo más reciente disponible para la clave (con caché por corrida)."""
    errores = []
    for url in candidatos(ARCHIVOS[clave]):
        try:
            r = requests.get(url, headers=CABECERAS, timeout=TIMEOUT)
        except requests.RequestException as e:
            errores.append(f"{url}: {e}")
            continue
        if r.status_code == 200 and r.content[:4] in FIRMAS:
            return r.content
        errores.append(f"{url}: HTTP {r.status_code}")
    raise RuntimeError(f"No se encontró el archivo {clave}: {errores[:3]}")


@lru_cache(maxsize=None)
def hojas(clave: str) -> dict[str, pd.DataFrame]:
    return pd.read_excel(io.BytesIO(bajar(clave)), sheet_name=None, header=None)


def _texto(v) -> str:
    return "" if pd.isna(v) else str(v).strip()


# ---------- Lectores ----------

def semestre_a_fecha(etiqueta: str) -> pd.Timestamp | None:
    """'1er. semestre 2017' -> 2017-01-01; '2do. semestre 2019 (1)' -> 2019-07-01."""
    m = re.search(r"(1|2)\D*semestre\D*(\d{4})", etiqueta, flags=re.I)
    if not m:
        return None
    return pd.Timestamp(int(m.group(2)), 1 if m.group(1) == "1" else 7, 1)


def indec_pobreza(campo: str, h: dict | None = None) -> pd.Series:
    """Cuadro 1 del informe de pobreza. campo: 'Pobreza/Personas', 'Indigencia/Hogares', etc."""
    df = (h or hojas("pobreza"))["Cuadro 1"]
    bloque, fila = campo.split("/")
    fila_enc = next(i for i in range(len(df)) if _texto(df.iat[i, 0]).lower() == "indicador")
    fechas = [semestre_a_fecha(_texto(v)) for v in df.iloc[fila_enc, 1:]]
    en_bloque = False
    for i in range(fila_enc + 1, len(df)):
        etiqueta = _texto(df.iat[i, 0])
        if etiqueta.lower() == bloque.lower():
            en_bloque = True
        elif en_bloque and etiqueta.lower() == fila.lower():
            valores = pd.to_numeric(df.iloc[i, 1:], errors="coerce").values
            s = pd.Series({f: v for f, v in zip(fechas, valores) if f is not None and pd.notna(v)}, dtype=float)
            return s.sort_index()
    raise ValueError(f"No se encontró {campo} en el cuadro de pobreza")


def indec_trimestral(df: pd.DataFrame, etiqueta: str, col_etiqueta: int = 1) -> pd.Series:
    """Cuadros anchos de cuentas nacionales: una fila de años y otra de trimestres."""
    fila_trim = next(i for i in range(len(df)) if any("trimestre" in _texto(v).lower() for v in df.iloc[i]))
    anios = pd.Series([_texto(v) for v in df.iloc[fila_trim - 1]]).replace("", pd.NA).ffill()
    fechas = {}
    for j, v in enumerate(df.iloc[fila_trim]):
        m = re.match(r"(\d)\D*trimestre", _texto(v).lower())
        a = re.match(r"(\d{4})", str(anios.iat[j])) if pd.notna(anios.iat[j]) else None
        if m and a:
            fechas[j] = pd.Timestamp(int(a.group(1)), 3 * (int(m.group(1)) - 1) + 1, 1)
    fila = next(i for i in range(fila_trim + 1, len(df))
                if _texto(df.iat[i, col_etiqueta]).lower().startswith(etiqueta.lower()))
    s = pd.Series({f: pd.to_numeric(df.iat[fila, j], errors="coerce") for j, f in fechas.items()}, dtype=float)
    return s.dropna().sort_index()


def indec_oferta_demanda(campo: str, h: dict | None = None) -> pd.Series:
    """Cuadro 1 (millones de pesos de 2004). campo: inicio de la fila, p. ej. 'Producto Interno Bruto'."""
    return indec_trimestral((h or hojas("oferta_demanda"))["cuadro 1"], campo)


def indec_canastas(campo: str, h: dict | None = None) -> pd.Series:
    """Serie de CBA y CBT por adulto equivalente. campo: 'CBT' o 'CBA'."""
    df = (h or hojas("canastas"))["CBA-CBT"]
    col = 3 if campo.upper() == "CBT" else 1
    fechas = pd.to_datetime(df.iloc[:, 0], errors="coerce", format="mixed")
    s = pd.Series(pd.to_numeric(df.iloc[:, col], errors="coerce").values, index=fechas)
    return s[s.index.notna()].dropna().sort_index()


def bcra_itcrm(campo: str = "ITCRM", h: dict | None = None) -> pd.Series:
    """Tipo de cambio real multilateral, promedio mensual (base 17-12-15 = 100)."""
    df = (h or hojas("itcrm"))["ITCRM y bilaterales prom. mens."]
    fila_enc = next(i for i in range(len(df)) if _texto(df.iat[i, 0]).lower() == "período")
    col = next(j for j, v in enumerate(df.iloc[fila_enc]) if _texto(v) == campo)
    fechas = pd.to_datetime(df.iloc[fila_enc + 1:, 0], errors="coerce", format="mixed")
    s = pd.Series(pd.to_numeric(df.iloc[fila_enc + 1:, col], errors="coerce").values, index=fechas)
    s = s[s.index.notna()].dropna()
    s.index = s.index.to_period("M").to_timestamp()
    return s.sort_index()


def indec_supermercados_provincias(h: dict | None = None) -> pd.DataFrame:
    """Cuadro 5: ventas totales a precios corrientes por jurisdicción (miles de pesos).
    Devuelve un DataFrame con una columna por jurisdicción e índice mensual."""
    df = (h or hojas("supermercados"))["Cuadro 5."]
    fila_jur = next(i for i in range(len(df)) if _texto(df.iat[i, 0]).lower() == "período")
    jur = pd.Series([_texto(v) for v in df.iloc[fila_jur]]).replace("", pd.NA).ffill()
    grupos = [_texto(v) for v in df.iloc[fila_jur + 1]]
    columnas = {jur.iat[j]: j for j in range(1, df.shape[1]) if grupos[j].lower() == "total" and pd.notna(jur.iat[j])}
    fechas = pd.to_datetime(df.iloc[fila_jur + 2:, 0], errors="coerce", format="mixed")
    datos = {n: pd.to_numeric(df.iloc[fila_jur + 2:, j], errors="coerce").values for n, j in columnas.items()}
    out = pd.DataFrame(datos, index=fechas)
    return out[out.index.notna()].dropna(how="all").sort_index()


def indec_supermercados_precios(h: dict | None = None) -> pd.Series:
    """Cuadro 2: índice de precios implícitos de supermercados (nacional, 2017=100)."""
    df = (h or hojas("supermercados"))["Cuadro 2"]
    fila = next(i for i in range(len(df)) if _texto(df.iat[i, 0]).lower() == "período")
    col = next(j for j, v in enumerate(df.iloc[fila]) if "precios implícitos" in _texto(v).lower())
    fechas = pd.to_datetime(df.iloc[fila + 1:, 0], errors="coerce", format="mixed")
    s = pd.Series(pd.to_numeric(df.iloc[fila + 1:, col], errors="coerce").values, index=fechas)
    s = s[s.index.notna()].dropna()
    s.index = s.index.to_period("M").to_timestamp()
    return s.sort_index()


LECTORES = {
    "indec_pobreza": indec_pobreza,
    "indec_oferta_demanda": indec_oferta_demanda,
    "indec_canastas": indec_canastas,
    "bcra_itcrm": bcra_itcrm,
}


def extraer(definicion: dict) -> pd.Series:
    return LECTORES[definicion["lector"]](definicion.get("campo"))
