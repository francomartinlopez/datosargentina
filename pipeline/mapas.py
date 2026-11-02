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


# ---------- Mapas con series: el sitio calcula cada vista (valor actual, interanual, gestión actual,
# desde el primer dato y por gestión) y dibuja la evolución de la provincia elegida ----------

def como_lista(s: pd.Series, desde: str = "2003-01-01", dec: int = 4) -> list:
    s = s.dropna().sort_index()
    s = s[s.index >= pd.Timestamp(desde)]
    return [[f.strftime("%Y-%m-%d"), round(float(v), dec)] for f, v in s.items()]


def mapa_serie(id_, nombre, seccion, series: dict[str, pd.Series], *, tipo_valor="nivel", frecuencia="M",
               unidad="", unidad_actual=None, escala_actual=1, dec_actual=1, fuente="", nota="", base="2023-11-01",
               actual: dict | None = None, regiones: dict | None = None, proyeccion: dict | None = None) -> dict:
    provincias = {n: como_lista(s) for n, s in series.items() if s is not None and not s.dropna().empty}
    if not provincias:
        raise ValueError("sin series")
    ultima = max(v[-1][0] for v in provincias.values())
    m = {"id": id_, "nombre": nombre, "seccion": seccion, "tipo": "serie", "tipo_valor": tipo_valor, "frecuencia": frecuencia,
         "unidad": unidad, "unidad_actual": unidad_actual or unidad, "escala_actual": escala_actual, "dec_actual": dec_actual,
         "fecha": ultima, "fuente": fuente, "nota": nota, "base": base, "provincias": provincias}
    if actual:
        m["actual"] = {k: round(float(v), 4) for k, v in actual.items() if v is not None and pd.notna(v)}
    if regiones:
        m["regiones"] = regiones
    if proyeccion:
        m["proyeccion"] = {n: como_lista(s) for n, s in proyeccion.items()}
    return m


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
    series = {}
    for col in df.columns:
        real = transformar.a_moneda_constante(df[col].dropna(), deflactor)
        series["Total del país" if col == "Total del país" else NOMBRES_IGN.get(col, col)] = real / 1e6
    return mapa_serie("supermercados_provincias", "Ventas en supermercados por provincia", "Actividad", series,
                      unidad="millones de pesos de hoy por mes", unidad_actual="millones de pesos de hoy, último mes", dec_actual=0, base=base,
                      fuente="INDEC, Encuesta de supermercados",
                      nota="Ventas a precios corrientes de cada jurisdicción deflactadas con el índice de precios implícitos nacional de supermercados (INDEC no publica precios por provincia). Series con estacionalidad: compará contra el mismo mes de otros años.")

PROVINCIAS = {
    "buenos_aires": "Buenos Aires", "caba": "Ciudad Autónoma de Buenos Aires", "catamarca": "Catamarca", "chaco": "Chaco",
    "chubut": "Chubut", "cordoba": "Córdoba", "corrientes": "Corrientes", "entre_rios": "Entre Ríos", "formosa": "Formosa",
    "jujuy": "Jujuy", "la_pampa": "La Pampa", "la_rioja": "La Rioja", "mendoza": "Mendoza", "misiones": "Misiones",
    "neuquen": "Neuquén", "rio_negro": "Río Negro", "salta": "Salta", "san_juan": "San Juan", "san_luis": "San Luis",
    "santa_cruz": "Santa Cruz", "santa_fe": "Santa Fe", "santiago_del_estero": "Santiago del Estero",
    "tierra_del_fuego": "Tierra del Fuego, Antártida e Islas del Atlántico Sur", "tucuman": "Tucumán",
}


def empleo(mensuales: dict, base: str) -> dict:
    series = {nombre: mensuales.get(f"asal_prov_{clave}") for clave, nombre in PROVINCIAS.items()}
    series["Total del país"] = mensuales.get("asalariados_privados_desest")
    series = {k: v for k, v in series.items() if v is not None and not v.empty}
    if len(series) < 2:
        raise ValueError("sin series de asalariados por provincia")
    return mapa_serie("empleo_provincias", "Empleo privado registrado por provincia", "Empleo e ingresos", series,
                      unidad="miles de asalariados", unidad_actual="miles de asalariados privados registrados", dec_actual=1, base=base,
                      fuente="SIPA (Ministerio de Capital Humano) vía datos.gob.ar",
                      nota="Series sin estacionalidad, salvo Entre Ríos, Formosa, Jujuy y San Juan (con estacionalidad: su variación mensual no es comparable). Cada trabajador se asigna a la provincia donde lo declara su empleador.")


# Regiones del IPC: la provincia de Buenos Aires se pinta con la región Pampeana (el GBA incluye
# los partidos del conurbano, que no se pueden separar en el mapa por provincia).
REGIONES_IPC = {
    "GBA": ["Ciudad Autónoma de Buenos Aires"],
    "Pampeana": ["Buenos Aires", "Córdoba", "Santa Fe", "Entre Ríos", "La Pampa"],
    "Noreste": ["Corrientes", "Chaco", "Formosa", "Misiones"],
    "Noroeste": ["Jujuy", "Salta", "Tucumán", "Catamarca", "Santiago del Estero", "La Rioja"],
    "Cuyo": ["Mendoza", "San Juan", "San Luis"],
    "Patagonia": ["Neuquén", "Río Negro", "Chubut", "Santa Cruz", "Tierra del Fuego, Antártida e Islas del Atlántico Sur"],
}


def inflacion_regiones(base: str) -> dict:
    from .fuentes import indec_api
    series = {r: indec_api.ipc(f"{r}|0") for r in REGIONES_IPC}
    series["Total del país"] = indec_api.ipc("Nacional|0")
    return mapa_serie("inflacion_regiones", "Inflación por región", "Precios", series, tipo_valor="indice",
                      unidad="índice dic-16 = 100", base=base, regiones=REGIONES_IPC,
                      fuente="INDEC, Índice de precios al consumidor (API de datos)",
                      nota="El IPC se mide en seis regiones. En el mapa, la provincia de Buenos Aires toma el valor de la región Pampeana y la Ciudad el del GBA (que también incluye los 24 partidos del conurbano). Serie desde diciembre de 2016.")


def poblacion(base: str) -> dict:
    from .fuentes import indec_api
    df = indec_api.poblacion_jurisdicciones()
    df["Total del país"] = df.sum(axis=1)
    hoy = pd.Timestamp.today()
    actual = df[df.index <= hoy]
    return mapa_serie("poblacion_provincias", "Población por provincia", "Población",
                      {c: actual[c] / 1000 for c in df.columns}, frecuencia="A",
                      unidad="miles de habitantes", unidad_actual=f"miles de habitantes, {actual.index[-1].year}", dec_actual=0,
                      base=f"{pd.Timestamp(base).year}-07-01",
                      proyeccion={c: df[c] / 1000 for c in df.columns},
                      fuente="INDEC, estimaciones y proyecciones de población 2022-2040 con base en el Censo 2022 (API de datos)",
                      nota="Población al 1° de julio de cada año. Hasta el año en curso son estimaciones; el gráfico sigue con la proyección del INDEC hasta 2040 (línea a partir del año próximo).")


def iibb_habitante(mensuales: dict, base: str) -> dict:
    from .fuentes import indec_api
    from .fuentes.archivos import JURISDICCIONES
    ipc = mensuales.get("ipc")
    pob = indec_api.poblacion_jurisdicciones()
    pob_hoy = pob[pob.index <= pd.Timestamp.today()].iloc[-1]
    series, actual = {}, {}
    nombres = {**{k: PROVINCIAS[k] for k in PROVINCIAS}, "total": "Total del país"}
    for clave in list(JURISDICCIONES) + ["total"]:
        s = mensuales.get(f"iibb_{clave}")
        if s is None or s.empty:
            continue
        real = transformar.acumulado_12m(transformar.a_moneda_constante(s, ipc))
        nombre = nombres[clave]
        series[nombre] = real
        hab = pob_hoy.sum() if clave == "total" else pob_hoy.get(nombre)
        if hab:
            actual[nombre] = real.iloc[-1] * 1e6 / hab
    return mapa_serie("iibb_provincias", "Ingresos Brutos por provincia", "Estado y fiscal", series,
                      unidad="millones de pesos de hoy, últimos 12 meses", unidad_actual="pesos de hoy por habitante, últimos 12 meses",
                      dec_actual=0, actual=actual, base=base,
                      fuente="Dirección Nacional de Recursos Provinciales (direcciones de rentas) y población del INDEC",
                      nota="«Valor actual»: recaudación de Ingresos Brutos de los últimos 12 meses dividida por la población estimada del año (INDEC). Las variaciones comparan la recaudación de 12 meses en pesos de hoy. Mensual desde 2017; el total del país se empalma antes de 2024 (ver la ficha de Ingresos Brutos).")

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
        "nota": "Administración pública no financiera de cada provincia, base devengado. Expresado en % de sus ingresos totales para poder comparar provincias de distinto tamaño."
                + (f" La Pampa no tiene datos de {a} publicados por Hacienda." if provincias.get("La Pampa", {}).get("resultado_financiero") is None else "")
                + (" Santiago del Estero muestra un superávit muy superior al resto, tal como lo publica Hacienda; puede reflejar diferencias en cómo registra sus cuentas." if (provincias.get("Santiago del Estero", {}).get("resultado_financiero") or 0) > 10 else ""),
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
              "fiscal": fiscal,
              "inflacion_regiones": lambda: inflacion_regiones(params["base_gestion_actual"]),
              "poblacion": lambda: poblacion(params["base_gestion_actual"]),
              "iibb": lambda: iibb_habitante(mensuales, params["base_gestion_actual"])}
    for nombre, funcion in tareas.items():
        try:
            mapa = funcion()
            (carpeta / f"{mapa['id']}.json").write_text(json.dumps(mapa, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        except Exception as e:
            alertas.append(f"mapa {nombre}: {e}")
    indice = sorted(p.stem for p in carpeta.glob("*.json") if p.stem not in ("provincias", "indice"))
    (carpeta / "indice.json").write_text(json.dumps(indice), encoding="utf-8")
    return alertas
