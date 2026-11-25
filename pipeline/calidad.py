"""Controles de calidad que se resumen en el informe de cada actualización."""
from __future__ import annotations

import pandas as pd


def revisar(nombre: str, nueva: pd.Series, anterior: pd.Series | None, umbral_desvios: float = 3.0,
            solo_historia: bool = False) -> list[str]:
    """Devuelve una lista de alertas (texto) para una serie mensual.

    solo_historia: la serie se usa solo para un tramo viejo de un empalme (p. ej. el IPC de San Luis
    entre 2007 y 2012); que no tenga datos nuevos no es un problema y no se avisa."""
    alertas = []
    nueva = nueva.dropna().sort_index()
    if nueva.empty:
        return [f"{nombre}: la fuente no devolvió datos"]

    if anterior is not None and not anterior.empty:
        anterior = anterior.dropna().sort_index()
        if nueva.index[-1] <= anterior.index[-1] and not solo_historia:
            alertas.append(f"{nombre}: sin dato nuevo (último {etiqueta_fecha(nueva)})")
        comunes = nueva.index.intersection(anterior.index)
        if len(comunes):
            a, b = nueva.loc[comunes], anterior.loc[comunes]
            cambiados = ((a - b).abs() > 1e-6 * b.abs().clip(lower=1)).sum()
            if cambiados:
                alertas.append(f"{nombre}: la fuente revisó {int(cambiados)} datos anteriores")

    alerta = salto_inusual(nombre, nueva, umbral_desvios)
    if alerta:
        alertas.append(alerta)
    return alertas


TRIMESTRES = {1: "I", 4: "II", 7: "III", 10: "IV"}


def etiqueta_fecha(s: pd.Series) -> str:
    """Último dato legible: '2026-09' en series mensuales, 'II trim. 2026' en trimestrales (que se
    fechan con el primer mes del trimestre), '2025' en anuales."""
    f = s.index[-1]
    pasos = s.index.to_series().diff().dt.days.dropna()
    paso = pasos.median() if len(pasos) else 31
    if paso > 300:
        return f"{f:%Y}"
    if paso > 80 and f.month in TRIMESTRES:
        return f"{TRIMESTRES[f.month]} trim. {f:%Y}"
    return f"{f:%Y-%m}"


def salto_inusual(nombre: str, s: pd.Series, umbral_desvios: float = 3.0) -> str | None:
    """Compara el último movimiento con la historia de la serie.

    Series siempre positivas (niveles, índices): variación %. Series con signo o que pasan cerca de
    cero (saldos, variaciones, tasas de cambio): la variación % no tiene sentido (de 10 a 3.700 da
    +35.000 %), así que se mira la diferencia en unidades de la serie."""
    con_signo = (s <= 0).any() or (s.abs() < 1e-9).any()
    mov = s.diff() if con_signo else s.pct_change()
    mov = mov.replace([float("inf"), float("-inf")], pd.NA).dropna()
    if len(mov) <= 24:
        return None
    historia, ultima = mov.iloc[:-1], mov.iloc[-1]
    desvio = historia.std()
    if not desvio or abs(ultima - historia.mean()) <= umbral_desvios * desvio:
        return None
    if con_signo:
        return (f"{nombre}: salto inusual en el último dato (de {s.iloc[-2]:,.1f} a {s.iloc[-1]:,.1f}; "
                f"{abs(ultima - historia.mean()) / desvio:.1f} desvíos de lo habitual)").replace(",", "·").replace(".", ",").replace("·", ".")
    return f"{nombre}: variación inusual en el último dato ({ultima * 100:.1f}%)"
