"""Normalización, empalmes, cálculos derivados y moneda constante."""
from __future__ import annotations

import pandas as pd


def a_mensual(s: pd.Series, agregacion: str = "promedio") -> pd.Series:
    """Lleva una serie (diaria o mensual) a una fecha por mes (día 1).

    agregacion: 'promedio' (tipo de cambio, tasas) o 'cierre' (stocks como reservas).
    Una serie que ya es mensual o trimestral queda igual, solo se normaliza la fecha al día 1.
    """
    if s.empty:
        return s
    clave = s.index.to_period("M")
    if agregacion == "cierre":
        m = s.groupby(clave).last()
    else:
        m = s.groupby(clave).mean()
    m.index = m.index.to_timestamp()
    return m.astype(float)


def empalmar(tramos: list[tuple[pd.Series, str | None]]) -> pd.Series:
    """Encadena índices de precios por sus variaciones mensuales.

    tramos: [(serie, hasta), ...] en orden cronológico. Cada tramo aporta las variaciones
    hasta su fecha 'hasta' (inclusive); el último no lleva 'hasta'. El resultado es un índice
    continuo que respeta exactamente la variación de cada fuente en su tramo, con el nivel
    del último tramo (la fuente vigente) intacto.
    """
    variaciones = []
    desde = None
    for serie, hasta in tramos:
        v = serie.sort_index().pct_change().dropna()
        if desde is not None:
            v = v[v.index > desde]
        if hasta is not None:
            v = v[v.index <= pd.Timestamp(hasta)]
            desde = pd.Timestamp(hasta)
        variaciones.append(v)
    var = pd.concat(variaciones)
    var = var[~var.index.duplicated(keep="last")].sort_index()
    esperado = pd.date_range(var.index[0], var.index[-1], freq="MS")
    faltan = esperado.difference(var.index)
    if len(faltan):
        raise ValueError(f"Empalme con huecos: faltan {len(faltan)} meses, el primero {faltan[0]:%Y-%m}")

    # Reconstruir el nivel hacia atrás desde el último dato de la fuente vigente
    ultimo = tramos[-1][0].sort_index().dropna()
    nivel_final = ultimo.iloc[-1]
    factores = (1 + var).cumprod()
    nivel = factores / factores.iloc[-1] * nivel_final
    # agregar el primer mes (base) que no tiene variación
    primero = var.index[0] - pd.DateOffset(months=1)
    nivel.loc[primero] = nivel.iloc[0] / (1 + var.iloc[0])
    return nivel.sort_index()


def calcular(operacion: str, a: pd.Series, b: pd.Series) -> pd.Series:
    a, b = a.align(b, join="inner")
    if operacion == "resta":
        return a - b
    if operacion == "brecha":  # en %
        return (a / b - 1) * 100
    if operacion == "cociente":
        return a / b
    raise ValueError(f"Operación desconocida: {operacion}")


def a_moneda_constante(s: pd.Series, deflactor: pd.Series) -> pd.Series:
    """Expresa una serie nominal en moneda del último mes con dato del deflactor.

    Para series trimestrales o con meses faltantes se usa el deflactor del mismo mes.
    Los meses sin deflactor quedan afuera (no se inventan valores).
    """
    d = deflactor.dropna().sort_index()
    base = d.iloc[-1]
    # Meses posteriores al último dato del deflactor (por ejemplo, reservas de octubre con IPC
    # hasta septiembre): se usa el último deflactor disponible, sin inventar inflación.
    if not s.empty and s.index[-1] > d.index[-1]:
        extra = pd.date_range(d.index[-1], s.index[-1], freq="MS")[1:]
        d = pd.concat([d, pd.Series(base, index=extra)])
    s, d = s.align(d, join="inner")
    return (s * base / d).dropna()


def acumulado_12m(s: pd.Series) -> pd.Series:
    """Suma móvil de 12 meses, para flujos fiscales muy estacionales (exige 12 meses completos)."""
    s = s.asfreq("MS")
    return s.rolling(12, min_periods=12).sum().dropna()
