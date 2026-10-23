"""Yahoo Finance (API pública de gráficos): cierres mensuales de índices y acciones.

Se usa para el Merval (^MERV, en pesos) y los ADR argentinos en Nueva York (en dólares).
"""
from __future__ import annotations

import pandas as pd

from . import pedir

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{simbolo}"


def parsear(j: dict) -> pd.Series:
    r = j["chart"]["result"][0]
    cierre = r["indicators"].get("adjclose", [{}])[0].get("adjclose") or r["indicators"]["quote"][0]["close"]
    fechas = pd.to_datetime(r["timestamp"], unit="s").to_period("M").to_timestamp()
    s = pd.Series(pd.to_numeric(cierre, errors="coerce"), index=fechas, dtype=float).dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def extraer(definicion: dict) -> pd.Series:
    j = pedir(URL.format(simbolo=definicion["id"]), {"range": "max", "interval": "1mo"}).json()
    return parsear(j)
