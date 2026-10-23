"""API de ArgentinaDatos (https://argentinadatos.com).

Endpoints usados:
  /v1/cotizaciones/dolares/{casa}   -> [{"casa","compra","venta","fecha"}]
  /v1/finanzas/indices/riesgo-pais  -> [{"valor","fecha"}]
"""
from __future__ import annotations

import pandas as pd

from . import pedir

BASE = "https://api.argentinadatos.com/v1/"


def parsear(registros: list, campo: str) -> pd.Series:
    if not registros:
        return pd.Series(dtype=float)
    fechas = pd.to_datetime([r["fecha"] for r in registros])
    valores = pd.to_numeric([r.get(campo) for r in registros], errors="coerce")
    s = pd.Series(valores, index=fechas, dtype=float).dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def extraer(definicion: dict) -> pd.Series:
    registros = pedir(BASE + definicion["id"]).json()
    return parsear(registros, definicion.get("campo", "valor"))
