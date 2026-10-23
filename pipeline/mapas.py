"""Mapas por provincia: variación intermensual, interanual y desde el inicio de la gestión actual.

Primer mapa: ventas en supermercados a precios corrientes por jurisdicción (INDEC), deflactadas
con el IPC nacional empalmado. La provincia de Buenos Aires suma los 24 partidos del Gran
Buenos Aires y el resto de la provincia.

Salida: sitio/public/datos/mapas/{id}.json
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import transformar
from .fuentes import archivos

NOMBRES_IGN = {"Tierra del Fuego": "Tierra del Fuego, Antártida e Islas del Atlántico Sur"}


def variaciones(s: pd.Series, base: str) -> dict:
    s = s.dropna().sort_index()
    ultimo, f = s.iloc[-1], s.index[-1]
    anterior = s.get(f - pd.DateOffset(months=1))
    hace_un_anio = s.get(f - pd.DateOffset(years=1))
    en_base = s.get(pd.Timestamp(base))
    pct = lambda a, b: None if b is None or pd.isna(b) or b == 0 else round(float((a / b - 1) * 100), 2)
    return {"intermensual": pct(ultimo, anterior), "interanual": pct(ultimo, hace_un_anio), "desde_gestion": pct(ultimo, en_base)}


def supermercados(ipc: pd.Series, base: str) -> dict:
    df = archivos.indec_supermercados_provincias()
    df.index = df.index.to_period("M").to_timestamp()
    if {"24 partidos del Gran Buenos Aires", "Resto de Buenos Aires"} <= set(df.columns):
        df["Buenos Aires"] = df.pop("24 partidos del Gran Buenos Aires") + df.pop("Resto de Buenos Aires")
    provincias = {}
    for col in df.columns:
        real = transformar.a_moneda_constante(df[col].dropna(), ipc)
        nombre = "Total del país" if col == "Total del país" else NOMBRES_IGN.get(col, col)
        provincias[nombre] = variaciones(real, base)
    return {
        "id": "supermercados_provincias",
        "nombre": "Ventas en supermercados por provincia",
        "seccion": "Actividad",
        "unidad": "variación % de las ventas a precios constantes",
        "fecha": df.index[-1].strftime("%Y-%m-%d"),
        "fuente": "INDEC, Encuesta de supermercados; deflactado con el IPC nacional",
        "nota": "Ventas a precios corrientes deflactadas con el IPC nacional (no hay precios provinciales para todo el período). La variación mensual no está desestacionalizada.",
        "provincias": provincias,
    }


def construir(mensuales: dict, params: dict, salida: Path) -> list[str]:
    """Genera los mapas disponibles. Devuelve alertas (un mapa que falla no frena el resto)."""
    alertas = []
    carpeta = salida / "mapas"
    carpeta.mkdir(parents=True, exist_ok=True)
    ipc = mensuales.get("ipc")
    for funcion in (supermercados,):
        try:
            mapa = funcion(ipc, params["base_gestion_actual"])
            (carpeta / f"{mapa['id']}.json").write_text(json.dumps(mapa, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        except Exception as e:
            alertas.append(f"mapa {funcion.__name__}: {e}")
    indice = sorted(p.stem for p in carpeta.glob("*.json") if p.stem not in ("provincias", "indice"))
    (carpeta / "indice.json").write_text(json.dumps(indice), encoding="utf-8")
    return alertas
