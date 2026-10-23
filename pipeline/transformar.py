"""Normalización, empalmes, cálculos derivados y moneda constante."""
from __future__ import annotations

import pandas as pd


def a_mensual(s: pd.Series, agregacion: str = "promedio") -> pd.Series:
    """Lleva una serie (diaria o mensual) a una fecha por mes (día 1).

    agregacion: 'promedio' (tipo de cambio, tasas), 'cierre' (stocks como reservas) o
    'suma' (flujos diarios, como las compras de divisas del BCRA; el mes en curso se descarta
    porque está incompleto).
    Una serie que ya es mensual o trimestral queda igual, solo se normaliza la fecha al día 1.
    """
    if s.empty:
        return s
    clave = s.index.to_period("M")
    if agregacion == "cierre":
        m = s.groupby(clave).last()
    elif agregacion == "suma":
        m = s.groupby(clave).sum()
        m = m[m.index < pd.Timestamp.today().to_period("M")]
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
    if operacion == "tasa_real":  # a = TNA en %, b = índice de precios; tasa real anualizada en %
        inflacion = b / b.shift(1) - 1
        real = (1 + a / 100 / 12) / (1 + inflacion) - 1
        return (((1 + real) ** 12 - 1) * 100).dropna()
    raise ValueError(f"Operación desconocida: {operacion}")


def a_moneda_constante(s: pd.Series, deflactor: pd.Series) -> pd.Series:
    """Expresa una serie nominal en moneda del último mes con dato del deflactor.

    Para series trimestrales o con meses faltantes se usa el deflactor del mismo mes.
    Los meses sin deflactor quedan afuera (no se inventan valores).
    """
    d = deflactor.dropna().sort_index()
    # Meses faltantes en el medio del deflactor (p. ej. el IPC de EE.UU. de octubre de 2025, que no
    # se publicó por el cierre del gobierno): se interpolan para no cortar la serie ni sus sumas.
    if len(d) > 2 and d.index.to_series().diff().dt.days.median() < 40:
        d = d.asfreq("MS").interpolate()
    base = d.iloc[-1]
    # Meses posteriores al último dato del deflactor (por ejemplo, reservas de octubre con IPC
    # hasta septiembre): se usa el último deflactor disponible, sin inventar inflación.
    if not s.empty and s.index[-1] > d.index[-1]:
        extra = pd.date_range(d.index[-1], s.index[-1], freq="MS")[1:]
        d = pd.concat([d, pd.Series(base, index=extra)])
    s, d = s.align(d, join="inner")
    return (s * base / d).dropna()


def acumulado_12m(s: pd.Series) -> pd.Series:
    """Suma móvil de 12 meses, para flujos fiscales muy estacionales (exige 12 meses completos).
    Si la serie es trimestral, suma los últimos 4 trimestres."""
    s = s.dropna().sort_index()
    if len(s) > 2 and s.index.to_series().diff().dt.days.median() > 60:
        s = s.asfreq("QS")
        return s.rolling(4, min_periods=4).sum().dropna()
    s = s.asfreq("MS")
    return s.rolling(12, min_periods=12).sum().dropna()


def porcentaje_pib(flujo: pd.Series, pib: pd.Series) -> pd.Series:
    """Flujo mensual acumulado en los 12 meses que terminan en cada trimestre, como % del PIB
    nominal de esos 4 trimestres. Resultado trimestral (fecha = primer mes del trimestre)."""
    f = flujo.dropna().sort_index()
    trimestral = len(f) > 2 and f.index.to_series().diff().dt.days.median() > 60
    if trimestral:  # flujo trimestral: suma de 4 trimestres, fechada al último mes de cada trimestre
        f12 = f.asfreq("QS").rolling(4, min_periods=4).sum()
        f12.index = f12.index + pd.DateOffset(months=2)
    else:
        f12 = f.asfreq("MS").rolling(12, min_periods=12).sum()
    # El PIB trimestral de INDEC en pesos corrientes se publica a tasa anual (cada trimestre
    # anualizado), así que el PIB de los últimos 4 trimestres es su promedio, no su suma.
    p4 = acumulado_12m(pib) / 4
    out = {}
    for q, v in p4.items():
        fin = q + pd.DateOffset(months=2)
        if fin in f12.index and pd.notna(f12[fin]) and v:
            out[q] = float(f12[fin] / v * 100)
    return pd.Series(out, dtype=float).sort_index()


def porcentaje_de(a: pd.Series, b: pd.Series, multiplicar: pd.Series | None = None, divisor_b: float = 1,
                  acumular: int = 1) -> pd.Series:
    """a (trimestral) como % de b (trimestral), con a convertida por una serie mensual opcional
    (p. ej. dólares a pesos con el promedio del tipo de cambio del trimestre)."""
    a = a.dropna()
    if multiplicar is not None:
        m = multiplicar.dropna()
        trimestral = m.groupby(m.index.to_period("Q")).mean()
        trimestral.index = trimestral.index.to_timestamp()
        a = a * trimestral.reindex(a.index)
    b = b.dropna() / divisor_b
    a, b = a.align(b, join="inner")
    if acumular > 1:  # suma de los últimos n períodos de cada una (suaviza flujos muy volátiles)
        a = a.rolling(acumular, min_periods=acumular).sum()
        b = b.rolling(acumular, min_periods=acumular).sum()
    return (a / b * 100).replace([float("inf"), -float("inf")], pd.NA).dropna().astype(float)
