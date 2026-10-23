"""Controles de calidad que se resumen en el informe de cada actualización."""
from __future__ import annotations

import pandas as pd


def revisar(nombre: str, nueva: pd.Series, anterior: pd.Series | None, umbral_desvios: float = 3.0) -> list[str]:
    """Devuelve una lista de alertas (texto) para una serie mensual."""
    alertas = []
    nueva = nueva.dropna().sort_index()
    if nueva.empty:
        return [f"{nombre}: la fuente no devolvió datos"]

    if anterior is not None and not anterior.empty:
        anterior = anterior.dropna().sort_index()
        if nueva.index[-1] <= anterior.index[-1]:
            alertas.append(f"{nombre}: sin dato nuevo (último {nueva.index[-1]:%Y-%m})")
        comunes = nueva.index.intersection(anterior.index)
        if len(comunes):
            a, b = nueva.loc[comunes], anterior.loc[comunes]
            cambiados = ((a - b).abs() > 1e-6 * b.abs().clip(lower=1)).sum()
            if cambiados:
                alertas.append(f"{nombre}: la fuente revisó {int(cambiados)} datos anteriores")

    var = nueva.pct_change().dropna()
    var = var[~var.isin([float("inf"), float("-inf")])]
    if len(var) > 24:
        historia, ultima = var.iloc[:-1], var.iloc[-1]
        desvio = historia.std()
        if desvio and abs(ultima - historia.mean()) > umbral_desvios * desvio:
            alertas.append(f"{nombre}: variación inusual en el último dato ({ultima * 100:.1f}%)")
    return alertas
