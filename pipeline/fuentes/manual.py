"""Carga manual: archivos CSV en data/manual/ con columnas fecha,valor,fuente_url.
Con escalonada: true, cada valor rige hasta el siguiente cambio (se completa mes a mes).

Se editan desde la web de GitHub. Una fila por dato.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

CARPETA = Path(__file__).resolve().parents[2] / "data" / "manual"


def extraer(definicion: dict) -> pd.Series:
    ruta = CARPETA / f"{definicion['id']}.csv"
    df = pd.read_csv(ruta)
    s = pd.Series(pd.to_numeric(df["valor"], errors="coerce").values,
                  index=pd.to_datetime(df["fecha"]), dtype=float).dropna()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    if definicion.get("escalonada"):
        # valor vigente al cierre de cada mes, hasta el mes actual (p. ej. una calificación)
        s = s.groupby(s.index.to_period("M")).last()
        meses = pd.period_range(s.index.min(), pd.Timestamp.today().to_period("M"), freq="M")
        s = s.reindex(meses).ffill()
        s.index = s.index.to_timestamp()
    return s
