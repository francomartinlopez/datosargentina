"""Cálculo de las vistas de cada indicador.

- intermensual: variación contra el período anterior (último dato)
- interanual: variación contra el mismo mes del año anterior (serie completa)
- gestion_actual: la misma serie que desde_2003, desde el primer mes del gobierno actual
- desde_2003: la serie en nivel desde mayo de 2003 (o el primer dato válido)
- comparativa: una serie por gestión con la variación interanual de cada mes,
  indexada por meses de mandato (1 = primer mes de gobierno)

Para tipo_valor 'tasa' las variaciones se expresan en diferencia de puntos y las
vistas de base son diferencias contra el mes base, no índices. Lo mismo para
'saldo' (montos que cambian de signo, como el resultado fiscal o el saldo
comercial): la variación es la diferencia en la misma unidad.

vista_historica = 'mensual' cambia la vista desde 2003 por la variación mensual
(se usa en los índices de precios, donde el nivel no es informativo).
"""
from __future__ import annotations

import math

import pandas as pd


def _es_tasa(tipo_valor: str) -> bool:
    """Tipos cuya variación se mide como diferencia y no como porcentaje."""
    return tipo_valor in ("tasa", "saldo")


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


def comparativa(ia: pd.Series, gestiones: list[dict]) -> dict:
    """{nombre_gestion: [[mes_de_mandato, variacion_interanual], ...]}.

    Cada gestión va desde el mes siguiente a su mes base hasta el mes base de la
    siguiente (el último mes completo de su mandato).
    """
    salida = {}
    for i, g in enumerate(gestiones):
        base_ts = pd.Timestamp(g["base"])
        fin = pd.Timestamp(gestiones[i + 1]["base"]) if i + 1 < len(gestiones) else None
        tramo = ia[ia.index > base_ts]
        if fin is not None:
            tramo = tramo[tramo.index <= fin]
        if tramo.empty:
            continue
        meses = [(f.year - base_ts.year) * 12 + (f.month - base_ts.month) for f in tramo.index]
        salida[g["nombre"]] = [[m, round(float(v), 4)] for m, v in zip(meses, tramo.values) if math.isfinite(v)]
    return salida


def como_lista(s: pd.Series | None) -> list:
    """Lista [fecha, valor] sin valores no finitos (una variación contra un período en cero
    da infinito, que no es JSON válido)."""
    if s is None:
        return []
    s = s.replace([float("inf"), float("-inf")], float("nan")).dropna()
    return [[f.strftime("%Y-%m-%d"), round(float(v), 4)] for f, v in s.items()]


def _finito(v: float | None) -> float | None:
    return v if v is not None and math.isfinite(v) else None


def mensual(s: pd.Series) -> pd.Series:
    return ((s / s.shift(1) - 1) * 100).dropna()


def calcular_vistas(s: pd.Series, tipo_valor: str, params: dict, gestiones: list[dict],
                    vista_historica: str = "nivel") -> dict:
    s = s.dropna().sort_index()
    inicio = pd.Timestamp(params["inicio_historico"]) - pd.DateOffset(months=1)
    ia = interanual(s, tipo_valor)
    historica = mensual(s) if vista_historica == "mensual" else s
    return {
        "intermensual": _finito(intermensual(s, tipo_valor)),
        "interanual_ultimo": _finito(float(ia.iloc[-1])) if not ia.empty else None,
        "vista_historica": vista_historica,
        "vistas": {
            "interanual": como_lista(ia[ia.index >= inicio]),
            "gestion_actual": como_lista(historica[historica.index > pd.Timestamp(params["base_gestion_actual"])]),
            "desde_2003": como_lista(historica[historica.index >= inicio]),
            "comparativa": comparativa(ia, gestiones),
        },
    }
