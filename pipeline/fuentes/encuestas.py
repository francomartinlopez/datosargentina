"""Encuestas de opinión: data/manual/encuestas_aprobacion.csv (una fila por encuesta).

Columnas: fecha, encuestadora, gestion, aprueba, desaprueba, muestra, lectura, fuente_url.
La serie mensual de una encuestadora es el promedio de sus mediciones del mes; el promedio general
es, para cada mes, el promedio simple de las encuestadoras que midieron ese mes.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

CARPETA = Path(__file__).resolve().parents[2] / "data" / "manual"


def tabla() -> pd.DataFrame:
    df = pd.read_csv(CARPETA / "encuestas_aprobacion.csv")
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["mes"] = df["fecha"].dt.to_period("M").dt.to_timestamp()
    for c in ("aprueba", "desaprueba"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["aprueba", "desaprueba"], how="all")


def extraer(definicion: dict) -> pd.Series:
    df = tabla()
    medida = definicion.get("medida", "aprueba")
    if medida == "neta":
        df["neta"] = df["aprueba"] - df["desaprueba"]
    quien = definicion.get("encuestadora", "promedio")
    if quien != "promedio":
        df = df[df["encuestadora"] == quien]
    por_encuestadora = df.groupby(["mes", "encuestadora"])[medida].mean()
    s = por_encuestadora.groupby(level="mes").mean()
    s.index = pd.DatetimeIndex(s.index)
    return s.dropna().sort_index().astype(float)
