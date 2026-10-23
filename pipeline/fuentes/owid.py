"""Our World in Data: series de FAO (hojas de balance de alimentos) por país.

Se usa para el consumo aparente por habitante de carnes y leche antes de que haya cifras
oficiales argentinas comparables. definicion: {id: <gráfico>, campo: <parte del nombre de columna>, pais: ARG}
"""
from __future__ import annotations

import io

import pandas as pd

from . import pedir

URL = "https://ourworldindata.org/grapher/{grafico}.csv"


def parsear(texto: str, campo: str, pais: str = "ARG") -> pd.Series:
    df = pd.read_csv(io.StringIO(texto))
    df = df[df["code"] == pais]
    col = next(c for c in df.columns if campo in c and not c.endswith("original_year"))
    s = pd.Series(pd.to_numeric(df[col], errors="coerce").values,
                  index=pd.to_datetime(df["year"].astype(int).astype(str) + "-01-01"), dtype=float).dropna()
    return s.sort_index()


def extraer(definicion: dict) -> pd.Series:
    texto = pedir(URL.format(grafico=definicion["id"]), {"v": 1, "csvType": "full", "useColumnShortNames": "true"}).text
    return parsear(texto, definicion["campo"], definicion.get("pais", "ARG"))
