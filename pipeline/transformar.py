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
    anual = len(var) > 1 and var.index.to_series().diff().dt.days.median() > 300
    esperado = pd.date_range(var.index[0], var.index[-1], freq="YS" if anual else "MS")
    faltan = esperado.difference(var.index)
    if len(faltan):
        raise ValueError(f"Empalme con huecos: faltan {len(faltan)} períodos, el primero {faltan[0]:%Y-%m}")

    # Reconstruir el nivel hacia atrás desde el último dato de la fuente vigente
    ultimo = tramos[-1][0].sort_index().dropna()
    nivel_final = ultimo.iloc[-1]
    factores = (1 + var).cumprod()
    nivel = factores / factores.iloc[-1] * nivel_final
    # agregar el primer mes (base) que no tiene variación
    primero = var.index[0] - (pd.DateOffset(years=1) if anual else pd.DateOffset(months=1))
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


def reservas_netas(reservas, encajes_balance, depositos_usd, swap_yuan, cny_por_usd, organismos, pases_balance,
                   pase_2016, swap_eeuu, desde_pases="2024-08-01") -> dict[str, pd.Series]:
    """Reservas netas (millones de US$, fin de mes) = brutas − encajes en dólares − swap con China −
    repos y pases en dólares − obligaciones con organismos internacionales − tramo activado del swap con EE.UU.

    Los rubros del balance del BCRA llegan con rezago: después del último mes publicado, los encajes se
    estiman con los depósitos privados en dólares y la proporción del último mes, y los repos y organismos
    se mantienen en su último valor. Devuelve también cada componente."""
    idx = reservas.dropna().index
    def mensual(s):
        return s.reindex(s.index.union(idx)).sort_index().ffill().reindex(idx) if s is not None and not s.empty else pd.Series(0.0, index=idx)
    ultimo_balance = encajes_balance.dropna().index.max()
    ratio = (encajes_balance / depositos_usd.reindex(encajes_balance.index)).dropna()
    encajes = encajes_balance.reindex(idx)
    if not ratio.empty:
        est = depositos_usd.reindex(idx) * ratio.iloc[-1]
        encajes = encajes.where(encajes.index <= ultimo_balance, est)
    swap = (mensual(swap_yuan) / mensual(cny_por_usd)).fillna(0)
    swap[idx < swap_yuan.index.min()] = 0
    pases = mensual(pases_balance)
    pases[idx < pd.Timestamp(desde_pases)] = 0
    repos = pases + mensual(pase_2016).fillna(0)
    org = mensual(organismos)
    org[idx < pd.Timestamp("2006-01-01")] = 0  # hasta 2005 el rubro es la deuda con el FMI, cancelada en enero de 2006
    eeuu = mensual(swap_eeuu).fillna(0)
    eeuu[idx < swap_eeuu.index.min()] = 0
    netas = reservas.reindex(idx) - encajes - swap - repos - org - eeuu
    return {"reservas_netas": netas.dropna(), "rn_encajes": encajes.dropna(), "rn_swap_china": swap,
            "rn_repos": repos, "rn_organismos": org, "rn_swap_eeuu": eeuu}


def presion_anual(nacional: pd.Series, provincial: pd.Series, pib: pd.Series, informalidad: pd.Series | None = None) -> dict[str, pd.Series]:
    """Presión tributaria anual en % del PIB: consolidada (recaudación nacional + impuestos propios de las
    provincias) y efectiva sobre la economía formal (consolidada dividida por la proporción de asalariados
    registrados, como aproximación del peso de la economía formal). nacional: flujo mensual; provincial: anual;
    pib: trimestral anualizado; informalidad: fracción trimestral de asalariados sin aportes."""
    n = nacional.dropna()
    nac = n.groupby(n.index.year).agg(["sum", "count"])
    nac = nac.loc[nac["count"] == 12, "sum"]
    p = pib.dropna()
    pa = p.groupby(p.index.year).agg(["mean", "count"])
    pa = pa.loc[pa["count"] == 4, "mean"]
    prov = provincial.dropna()
    prov.index = prov.index.year
    anios = sorted(set(nac.index) & set(pa.index) & set(prov.index))
    idx = pd.to_datetime([f"{a}-01-01" for a in anios])
    consolidada = pd.Series([(nac[a] + prov[a]) / pa[a] * 100 for a in anios], index=idx, dtype=float)
    salida = {"presion_consolidada": consolidada,
              "presion_provincial": pd.Series([prov[a] / pa[a] * 100 for a in anios], index=idx, dtype=float)}
    if informalidad is not None and not informalidad.dropna().empty:
        inf = informalidad.dropna()
        ia = inf.groupby(inf.index.year).mean()
        a2 = [a for a in anios if a in ia.index]
        salida["presion_efectiva_formal"] = pd.Series([consolidada[pd.Timestamp(a, 1, 1)] / (1 - ia[a]) for a in a2],
                                                      index=pd.to_datetime([f"{a}-01-01" for a in a2]), dtype=float)
    return salida


def indice_equiponderado(series: list[pd.Series], base: str = "2003-12-01") -> pd.Series:
    """Índice de precios equiponderado: cada mes, promedio simple de las variaciones de las acciones que
    cotizan ese mes y el anterior, encadenado. Base 100 en el mes indicado (o el primero disponible)."""
    df = pd.concat([s.dropna() for s in series], axis=1).sort_index()
    var = df.pct_change(fill_method=None)
    prom = var.mean(axis=1, skipna=True).dropna()
    nivel = (1 + prom).cumprod()
    nivel = pd.concat([pd.Series([1.0], index=[df.index[0]]), nivel])
    b = pd.Timestamp(base)
    ref = nivel[b] if b in nivel.index else nivel.iloc[0]
    return (nivel / ref * 100).astype(float)
