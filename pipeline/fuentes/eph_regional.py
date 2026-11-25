"""Desocupación y tasa de empleo de los aglomerados de Santa Fe, Córdoba y el AMBA (EPH del INDEC).

Se calculan con los microdatos de cada trimestre, igual que la publicación oficial:
- desocupación = desocupados / población económicamente activa (ocupados + desocupados);
- tasa de empleo = ocupados / población total;
ambas ponderadas con PONDERA. Bases: 2003-T3 a 2015-T2 en Stata (.zip o .rar) y desde 2016-T2 en
texto (no hay bases de 2015-T3 a 2016-T1, por la emergencia estadística).

Resultados por trimestre en data/derivados/eph_regional.csv; en cada corrida solo se agregan los
trimestres que faltan.
"""
from __future__ import annotations

import io
import zipfile
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path(__file__).resolve().parents[2] / "data" / "derivados" / "eph_regional.csv"
DESDE = (2003, 3)
AGLOMERADOS = {4: "gran_rosario", 5: "gran_santa_fe", 13: "gran_cordoba", 32: "caba", 33: "partidos_gba"}
COLS = ["AGLOMERADO", "ESTADO", "PONDERA"]


def tasas(df: pd.DataFrame) -> dict:
    df = df.copy()
    df.columns = [str(c).strip().upper() for c in df.columns]
    for c in COLS:
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", "."), errors="coerce")
    fila = {}
    for cod, nombre in AGLOMERADOS.items():
        a = df[df["AGLOMERADO"] == cod]
        w, est = a["PONDERA"], a["ESTADO"]
        ocup, desoc, total = w[est == 1].sum(), w[est == 2].sum(), w.sum()
        fila[f"desocupacion_{nombre}"] = 100 * desoc / (ocup + desoc) if ocup + desoc else np.nan
        fila[f"empleo_{nombre}"] = 100 * ocup / total if total else np.nan
        fila[f"casos_{nombre}"] = int(len(a))
    return fila


def leer(anio: int, trim: int) -> pd.DataFrame | None:
    from . import eph_panel
    if (anio, trim) < (2016, 2):
        base = f"t{trim}{str(anio)[2:]}_dta"
        for ext in ("zip", "rar"):
            c = eph_panel._bajar(f"{base}.{ext}")
            if c:
                archivos = [f for f in eph_panel._extraer(c, ext) if f.lower().endswith(".dta") and eph_panel._es_personas(f)]
                if archivos:
                    df = pd.read_stata(archivos[0], convert_categoricals=False)
                    df.columns = [str(x).strip().upper() for x in df.columns]
                    return df[[c for c in COLS if c in df.columns]]
        return None
    from .archivos import _eph_zip
    c = _eph_zip(anio, trim)
    if c is None:
        return None
    z = zipfile.ZipFile(io.BytesIO(c))
    nombres = [n for n in z.namelist() if eph_panel._es_personas(n) and n.lower().endswith((".txt", ".csv"))]
    if not nombres:
        return None
    crudo = z.open(nombres[0]).read()
    sep = ";" if crudo[:2000].count(b";") > crudo[:2000].count(b",") else ","
    return pd.read_csv(io.BytesIO(crudo), sep=sep, low_memory=False, encoding="latin-1", usecols=lambda x: x.strip().upper() in COLS)


@lru_cache(maxsize=None)
def tabla() -> pd.DataFrame:
    previo = pd.read_csv(CACHE, dtype={"trimestre": str}) if CACHE.exists() else pd.DataFrame(columns=["trimestre"])
    hechos = set(previo["trimestre"])
    hoy = pd.Timestamp.today()
    nuevos, (a, t) = [], DESDE
    while (a, t) <= (hoy.year, (hoy.month - 1) // 3 + 1):
        clave = f"{a}-T{t}"
        if clave not in hechos and not ((2015, 3) <= (a, t) <= (2016, 1)):
            try:
                df = leer(a, t)
                if df is not None:
                    nuevos.append({"trimestre": clave, **tasas(df)})
            except Exception:
                pass  # un trimestre con formato distinto no frena el resto; se reintenta en la próxima corrida
        a, t = (a + 1, 1) if t == 4 else (a, t + 1)
    if not nuevos:
        return previo
    out = pd.concat([previo, pd.DataFrame(nuevos)], ignore_index=True).sort_values("trimestre")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(CACHE, index=False)
    return out


def serie(campo: str) -> pd.Series:
    """campo: 'desocupacion_gran_rosario', 'empleo_caba', etc. Fecha: primer mes del trimestre."""
    t = tabla()
    if campo not in t.columns:
        raise ValueError(f"EPH regional: no hay {campo}")
    fechas = [pd.Timestamp(int(x[:4]), 3 * int(x[-1]) - 2, 1) for x in t["trimestre"]]
    return pd.Series(pd.to_numeric(t[campo], errors="coerce").values, index=fechas, dtype=float).dropna().sort_index()
