"""Cálculo de las vistas de cada indicador.

- intermensual: variación contra el período anterior (último dato)
- interanual: variación contra el mismo mes del año anterior (serie completa)
- gestion_actual: base 100 en el mes previo a la asunción del gobierno actual
- desde_2003: la serie en nivel desde mayo de 2003 (o el primer dato válido)
- comparativa: una serie por gestión, base 100 el mes previo a la asunción,
  indexada por meses transcurridos desde la asunción

Para tipo_valor 'tasa' las variaciones se expresan en diferencia de puntos y las
vistas de base son diferencias contra el mes base, no índices.
"""
from __future__ import annotations

import pandas as pd


def _es_tasa(tipo_valor: str) -> bool:
    return tipo_valor == "tasa"


def interanual(s: pd.Series, tipo_valor: str) -> pd.Series:
    anterior = s.copy()
    anterior.index = anterior.index + pd.DateOffset(years=1)
    a, b = s.align(anterior, join="inner")
    if _es_tasa(tipo_valor):
        return (a - b).dropna()
    return ((a / b - 1) * 100).dropna()


def intermensual(s: pd.Series, tipo_valor: str) -> float | None:
    """Variación del último período contra el anterior (mes o trimestre según la serie)."""
    s = s.dropna()
    if len(s) < 2:
        return None
    ultimo, previo = s.iloc[-1], s.iloc[-2]
    if _es_tasa(tipo_valor):
        return float(ultimo - previo)
    if previo == 0:
        return None
    return float((ultimo / previo - 1) * 100)


def desde_base(s: pd.Series, base: str, tipo_valor: str) -> pd.Series | None:
    """Índice base 100 (o diferencia en puntos) desde el mes base. None si no hay dato base."""
    base_ts = pd.Timestamp(base)
    s = s.dropna()
    tramo = s[s.index >= base_ts]
    if tramo.empty:
        return None
    # dato base: el del mes base o, si es trimestral, el último disponible hasta ese mes
    previos = s[s.index <= base_ts]
    if previos.empty:
        return None
    valor_base = previos.iloc[-1]
    if _es_tasa(tipo_valor):
        return tramo - valor_base
    if valor_base == 0:
        return None
    return tramo / valor_base * 100


def comparativa(s: pd.Series, gestiones: list[dict], tipo_valor: str) -> dict:
    """{nombre_gestion: [[meses_desde_asuncion, valor], ...]} recortado al fin de cada mandato."""
    salida = {}
    for i, g in enumerate(gestiones):
        fin = pd.Timestamp(gestiones[i + 1]["base"]) if i + 1 < len(gestiones) else None
        tramo = desde_base(s, g["base"], tipo_valor)
        if tramo is None:
            continue
        if fin is not None:
            tramo = tramo[tramo.index <= fin]
        base_ts = pd.Timestamp(g["base"])
        meses = [(f.year - base_ts.year) * 12 + (f.month - base_ts.month) for f in tramo.index]
        salida[g["nombre"]] = [[m, round(float(v), 4)] for m, v in zip(meses, tramo.values)]
    return salida


def como_lista(s: pd.Series | None) -> list:
    if s is None:
        return []
    return [[f.strftime("%Y-%m-%d"), round(float(v), 4)] for f, v in s.dropna().items()]


def calcular_vistas(s: pd.Series, tipo_valor: str, params: dict, gestiones: list[dict]) -> dict:
    s = s.dropna().sort_index()
    inicio = pd.Timestamp(params["inicio_historico"])
    return {
        "intermensual": intermensual(s, tipo_valor),
        "interanual_ultimo": (lambda ia: float(ia.iloc[-1]) if not ia.empty else None)(interanual(s, tipo_valor)),
        "vistas": {
            "interanual": como_lista(interanual(s, tipo_valor)),
            "gestion_actual": como_lista(desde_base(s, params["base_gestion_actual"], tipo_valor)),
            "desde_2003": como_lista(s[s.index >= inicio - pd.DateOffset(months=1)]),
            "comparativa": comparativa(s, gestiones, tipo_valor),
        },
    }
