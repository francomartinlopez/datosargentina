"""API de Principales Variables del BCRA, versión 4.

Base: https://api.bcra.gob.ar/estadisticas/v4.0/monetarias/{idVariable}
Devuelve como máximo 3000 registros por pedido, así que se pide por tramos de fechas.
"""
from __future__ import annotations

import os
from datetime import date

import pandas as pd

from . import pedir

URL = "https://api.bcra.gob.ar/estadisticas/v4.0/monetarias/{id}"
LIMITE = 3000
# El certificado del BCRA a veces falla con la cadena de CA de Python; se puede desactivar
# la verificación con BCRA_VERIFICAR_SSL=0 (solo afecta a este extractor).
VERIFICAR = os.environ.get("BCRA_VERIFICAR_SSL", "1") != "0"


def parsear(payload: dict) -> pd.Series:
    """Acepta las dos formas conocidas de respuesta:
    v4: results = [{"idVariable": 1, "detalle": [{"fecha": ..., "valor": ...}]}]
    v3: results = [{"idVariable": 1, "fecha": ..., "valor": ...}, ...]
    """
    resultados = payload.get("results", [])
    registros = []
    for r in resultados:
        if isinstance(r, dict) and "detalle" in r:
            registros.extend(r["detalle"])
        else:
            registros.append(r)
    if not registros:
        return pd.Series(dtype=float)
    fechas = pd.to_datetime([r["fecha"] for r in registros])
    valores = pd.to_numeric([r["valor"] for r in registros], errors="coerce")
    s = pd.Series(valores, index=fechas, dtype=float).dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def extraer(definicion: dict, desde: str = "1996-01-01") -> pd.Series:
    partes = []
    inicio = pd.Timestamp(desde)
    hoy = pd.Timestamp(date.today())
    while inicio <= hoy:
        fin = min(inicio + pd.DateOffset(years=8), hoy)  # 8 años de datos diarios < 3000 filas
        params = {"desde": inicio.strftime("%Y-%m-%d"), "hasta": fin.strftime("%Y-%m-%d"), "limit": LIMITE}
        payload = pedir(URL.format(id=definicion["id"]), params, verify=VERIFICAR).json()
        partes.append(parsear(payload))
        inicio = fin + pd.Timedelta(days=1)
    serie = pd.concat(partes) if partes else pd.Series(dtype=float)
    return serie[~serie.index.duplicated(keep="last")].sort_index()
