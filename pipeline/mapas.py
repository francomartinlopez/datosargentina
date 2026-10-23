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
    # Deflactor: precios implícitos de los supermercados (así el total coincide con el índice a
    # precios constantes de INDEC); si no está, el IPC nacional.
    try:
        deflactor = archivos.indec_supermercados_precios()
    except Exception:
        deflactor = ipc
    provincias = {}
    for col in df.columns:
        real = transformar.a_moneda_constante(df[col].dropna(), deflactor)
        nombre = "Total del país" if col == "Total del país" else NOMBRES_IGN.get(col, col)
        provincias[nombre] = variaciones(real, base)
    return {
        "id": "supermercados_provincias",
        "nombre": "Ventas en supermercados por provincia",
        "seccion": "Actividad",
        "unidad": "variación % de las ventas a precios constantes",
        "fecha": df.index[-1].strftime("%Y-%m-%d"),
        "fuente": "INDEC, Encuesta de supermercados",
        "nota": "Ventas a precios corrientes de cada jurisdicción deflactadas con el índice de precios implícitos nacional de supermercados (INDEC no publica precios por provincia). La variación mensual no está desestacionalizada.",
        "provincias": provincias,
    }


PROVINCIAS = {
    "buenos_aires": "Buenos Aires", "caba": "Ciudad Autónoma de Buenos Aires", "catamarca": "Catamarca", "chaco": "Chaco",
    "chubut": "Chubut", "cordoba": "Córdoba", "corrientes": "Corrientes", "entre_rios": "Entre Ríos", "formosa": "Formosa",
    "jujuy": "Jujuy", "la_pampa": "La Pampa", "la_rioja": "La Rioja", "mendoza": "Mendoza", "misiones": "Misiones",
    "neuquen": "Neuquén", "rio_negro": "Río Negro", "salta": "Salta", "san_juan": "San Juan", "san_luis": "San Luis",
    "santa_cruz": "Santa Cruz", "santa_fe": "Santa Fe", "santiago_del_estero": "Santiago del Estero",
    "tierra_del_fuego": "Tierra del Fuego, Antártida e Islas del Atlántico Sur", "tucuman": "Tucumán",
}


def empleo(mensuales: dict, base: str) -> dict:
    provincias = {}
    for clave, nombre in PROVINCIAS.items():
        s = mensuales.get(f"asal_prov_{clave}")
        if s is not None and not s.empty:
            provincias[nombre] = variaciones(s, base)
    total = mensuales.get("asalariados_privados_desest")
    if total is not None and not total.empty:
        provincias["Total del país"] = variaciones(total, base)
    fechas = [mensuales[f"asal_prov_{c}"].index[-1] for c in PROVINCIAS if mensuales.get(f"asal_prov_{c}") is not None]
    if not provincias or not fechas:
        raise ValueError("sin series de asalariados por provincia")
    return {
        "id": "empleo_provincias",
        "nombre": "Empleo privado registrado por provincia",
        "seccion": "Empleo e ingresos",
        "unidad": "variación % de los asalariados privados registrados",
        "fecha": max(fechas).strftime("%Y-%m-%d"),
        "fuente": "SIPA (Ministerio de Capital Humano) vía datos.gob.ar",
        "nota": "Series sin estacionalidad, salvo Entre Ríos, Formosa, Jujuy y San Juan (con estacionalidad: su variación mensual no es comparable). Cada trabajador se asigna a la provincia donde lo declara su empleador.",
        "provincias": provincias,
    }


HOJAS_IGN = {"Ciudad": "Ciudad Autónoma de Buenos Aires", "Tierra del Fuego": "Tierra del Fuego, Antártida e Islas del Atlántico Sur",
             "Consolidado": "Total del país"}


def fiscal() -> dict:
    """Resultado fiscal y dependencia de recursos nacionales por provincia (último año y cambio desde 2023)."""
    hojas = archivos.provincias_serie()
    ultimo = max(df.index.max() for df in hojas.values())
    base = pd.Timestamp(2023, 1, 1)
    provincias = {}
    for hoja, df in hojas.items():
        nombre = HOJAS_IGN.get(hoja, hoja)
        if ultimo not in df.index:
            continue
        pct = lambda c, f: (round(float(df.at[f, c] / df.at[f, "ingresos_totales"] * 100), 2)
                            if f in df.index and df.at[f, "ingresos_totales"] else None)
        rf, rf_base = pct("resultado_financiero", ultimo), pct("resultado_financiero", base)
        provincias[nombre] = {
            "resultado_financiero": rf,
            "resultado_primario": pct("resultado_primario", ultimo),
            "cambio_financiero": round(rf - rf_base, 2) if rf is not None and rf_base is not None else None,
            "origen_nacional": pct("tributarios_nacionales", ultimo),
        }
    a = ultimo.year
    return {
        "id": "fiscal_provincias",
        "nombre": "Cuentas fiscales de las provincias",
        "seccion": "Estado y fiscal",
        "unidad": "% de los ingresos totales de cada provincia",
        "fecha": ultimo.strftime("%Y-%m-%d"),
        "periodo": str(a),
        "fuente": "Secretaría de Hacienda, Coordinación Fiscal Provincial (esquema ahorro-inversión-financiamiento)",
        "nota": "Administración pública no financiera de cada provincia, base devengado. Expresado en % de sus ingresos totales para poder comparar provincias de distinto tamaño.",
        "vistas": [
            {"id": "resultado_financiero", "texto": f"Resultado financiero {a}", "desc": f"Resultado financiero (después de intereses) en % de los ingresos, {a}.", "sufijo": "%"},
            {"id": "resultado_primario", "texto": f"Resultado primario {a}", "desc": f"Resultado primario (antes de intereses) en % de los ingresos, {a}.", "sufijo": "%"},
            {"id": "cambio_financiero", "texto": "Cambio desde 2023", "desc": f"Cambio del resultado financiero entre 2023 y {a}, en puntos porcentuales de los ingresos.", "sufijo": " pp"},
            {"id": "origen_nacional", "texto": "Recursos nacionales", "desc": f"Coparticipación y otros impuestos nacionales que recibe cada provincia, en % de sus ingresos, {a}.", "sufijo": "%", "secuencial": True},
        ],
        "provincias": provincias,
    }


def construir(mensuales: dict, params: dict, salida: Path) -> list[str]:
    """Genera los mapas disponibles. Devuelve alertas (un mapa que falla no frena el resto)."""
    alertas = []
    carpeta = salida / "mapas"
    carpeta.mkdir(parents=True, exist_ok=True)
    ipc = mensuales.get("ipc")
    tareas = {"supermercados": lambda: supermercados(ipc, params["base_gestion_actual"]),
              "empleo": lambda: empleo(mensuales, params["base_gestion_actual"]),
              "fiscal": fiscal}
    for nombre, funcion in tareas.items():
        try:
            mapa = funcion()
            (carpeta / f"{mapa['id']}.json").write_text(json.dumps(mapa, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        except Exception as e:
            alertas.append(f"mapa {nombre}: {e}")
    indice = sorted(p.stem for p in carpeta.glob("*.json") if p.stem not in ("provincias", "indice"))
    (carpeta / "indice.json").write_text(json.dumps(indice), encoding="utf-8")
    return alertas
