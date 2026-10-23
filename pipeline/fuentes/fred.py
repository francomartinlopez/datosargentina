"""FRED (Reserva Federal de St. Louis): descarga CSV pública, sin clave.

Se usa para el IPC de Estados Unidos (CPIAUCSL), deflactor de los valores en dólares.
"""
from __future__ import annotations

import io

import pandas as pd

from . import pedir

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def parsear(texto: str, serie_id: str) -> pd.Series:
    df = pd.read_csv(io.StringIO(texto))
    col_fecha = df.columns[0]  # "observation_date" o "DATE" según la versión
    col_valor = serie_id if serie_id in df.columns else df.columns[1]
    s = pd.Series(pd.to_numeric(df[col_valor], errors="coerce").values,
                  index=pd.to_datetime(df[col_fecha]), dtype=float).dropna()
    return s.sort_index()


def extraer(definicion: dict) -> pd.Series:
    texto = pedir(URL, {"id": definicion["id"]}).text
    return parsear(texto, definicion["id"])
