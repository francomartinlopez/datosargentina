"""Yahoo Finance (API pública de gráficos): cierres mensuales de índices y acciones.

Se usa para el Merval (^MERV, en pesos) y los ADR argentinos en Nueva York (en dólares).
"""
from __future__ import annotations

import pandas as pd

from . import pedir

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{simbolo}"


def parsear(j: dict) -> pd.Series:
    r = j["chart"]["result"][0]
    fechas = pd.to_datetime(r["timestamp"], unit="s").to_period("M").to_timestamp()
    # se usa el cierre ajustado si viene completo; si Yahoo lo manda casi vacío, el cierre común
    candidatas = [r["indicators"].get("adjclose", [{}])[0].get("adjclose"), r["indicators"]["quote"][0].get("close")]
    series = [pd.Series(pd.to_numeric(c, errors="coerce"), index=fechas, dtype=float).dropna() for c in candidatas if c]
    s = max(series, key=len) if series else pd.Series(dtype=float)
    return s[~s.index.duplicated(keep="last")].sort_index()


def extraer(definicion: dict) -> pd.Series:
    # Desde noviembre de 2026 Yahoo devuelve un solo dato con range=max para el Merval; con un rango
    # de fechas explícito trae al menos los últimos meses, que se suman a la historia guardada
    # (ver construir.combinar_con_anterior).
    hasta = int(pd.Timestamp.now(tz="UTC").timestamp())
    j = pedir(URL.format(simbolo=definicion["id"]), {"period1": 946684800, "period2": hasta, "interval": "1mo"}).json()
    return parsear(j)
