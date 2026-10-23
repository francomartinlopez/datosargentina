"""Carga manual: archivos CSV en data/manual/ con columnas fecha,valor,fuente_url.

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
    return s[~s.index.duplicated(keep="last")].sort_index()
