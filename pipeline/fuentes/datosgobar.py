"""API de Series de Tiempo de datos.gob.ar.

Documentación: https://series-tiempo-ar-api-english.readthedocs.io/
"""
from __future__ import annotations

import time

import pandas as pd

from . import pedir

URL = "https://apis.datos.gob.ar/series/api/series/"
LIMITE = 1000  # máximo de filas por página que acepta la API


def parsear(payload: dict) -> pd.Series:
    filas = payload.get("data", [])
    if not filas:
        return pd.Series(dtype=float)
    fechas = pd.to_datetime([f[0] for f in filas])
    valores = pd.to_numeric([f[1] for f in filas], errors="coerce")
    s = pd.Series(valores, index=fechas, dtype=float).dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def extraer(definicion: dict, reintentos: int = 3) -> pd.Series:
    """La API a veces devuelve una respuesta vacía para una serie que existe (sobre todo
    con muchos pedidos seguidos): se reintenta unas veces con espera antes de darla por vacía."""
    for intento in range(reintentos):
        s = _extraer(definicion)
        if not s.empty:
            return s
        time.sleep(5 * (intento + 1))
    return s


def _extraer(definicion: dict) -> pd.Series:
    partes = []
    inicio = 0
    while True:
        params = {"ids": definicion["id"], "format": "json", "limit": LIMITE, "start": inicio}
        payload = pedir(URL, params).json()
        s = parsear(payload)
        partes.append(s)
        total = payload.get("count", 0)
        inicio += LIMITE
        if inicio >= total or s.empty:
            break
    serie = pd.concat(partes) if partes else pd.Series(dtype=float)
    return serie[~serie.index.duplicated(keep="last")].sort_index()
