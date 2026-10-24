"""Imagen de dirigentes políticos según encuestas (data/manual/encuestas_imagen.csv).

Para cada dirigente se toma la medición más reciente de cada encuestadora dentro de los
últimos 3 meses (contados desde la encuesta más reciente cargada) y se promedia.
Salida: sitio/public/datos/encuestas_imagen.json
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

ARCHIVO = Path(__file__).resolve().parents[1] / "data" / "manual" / "encuestas_imagen.csv"
VENTANA_MESES = 3


def resumen(df: pd.DataFrame) -> dict:
    df = df.copy()
    df["fecha"] = pd.to_datetime(df["fecha"])
    for c in ("positiva", "negativa"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["positiva", "negativa"])
    tope = df["fecha"].max()
    reciente = df[df["fecha"] > tope - pd.DateOffset(months=VENTANA_MESES)]
    ult = reciente.sort_values("fecha").groupby(["figura", "encuestadora"]).tail(1)
    filas = []
    for fig, g in ult.groupby("figura"):
        filas.append({"figura": fig, "positiva": round(g["positiva"].mean(), 1), "negativa": round(g["negativa"].mean(), 1),
                      "diferencial": round((g["positiva"] - g["negativa"]).mean(), 1), "n": int(len(g)),
                      "mediciones": [{"encuestadora": r.encuestadora, "fecha": r.fecha.date().isoformat(), "positiva": float(r.positiva),
                                      "negativa": float(r.negativa), "fuente": r.fuente_url} for r in g.sort_values("encuestadora").itertuples()]})
    filas.sort(key=lambda f: (f["n"] < 2, -f["positiva"]))
    encuestadoras = sorted(ult["encuestadora"].unique())
    return {"desde": (tope - pd.DateOffset(months=VENTANA_MESES - 1)).date().replace(day=1).isoformat(), "hasta": tope.date().isoformat(),
            "encuestadoras": encuestadoras, "figuras": filas}


PROBLEMAS = ARCHIVO.parent / "espop_problemas.csv"
MOSTRAR = [("inseguridad", "Inseguridad"), ("falta_trabajo", "Falta de trabajo"), ("inflacion", "Inflación"),
           ("bajos_salarios", "Bajos salarios"), ("corrupcion", "Corrupción")]


def construir_problemas(salida: Path) -> list[str]:
    try:
        df = pd.read_csv(PROBLEMAS)
        series = []
        for clave, nombre in MOSTRAR:
            g = df[df["problema"] == clave].sort_values("fecha")
            series.append({"clave": clave, "nombre": nombre, "puntos": [[r.fecha, float(r.porcentaje)] for r in g.itertuples()]})
        d = {"id": "principales_problemas", "nombre": "Principales problemas del país según la gente", "seccion": "Opinión pública",
             "unidad": "% que lo menciona entre los principales problemas", "fecha": date.today().isoformat(), "series": series,
             "fuente": "UdeSA, Encuesta de Satisfacción Política y Opinión Pública (ESPOP)",
             "fuente_url": str(df["fuente_url"].iloc[-1]),
             "nota": "Pregunta: ¿cuál o cuáles dirías que son los principales problemas que afectan hoy al país? Se puede elegir más de uno, por eso los porcentajes no suman 100. Encuesta online de UdeSA (1.000 casos por medición) desde junio de 2018. Los valores históricos se leyeron del gráfico evolutivo del último informe y pueden diferir en ±1 punto; la última medición es el dato publicado. La serie de pobreza también está en los datos descargables."}
        (salida / "encuestas_problemas.json").write_text(json.dumps(d, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        return []
    except Exception as e:
        return [f"Encuestas (problemas): {e}"]


def construir(salida: Path) -> list[str]:
    try:
        d = resumen(pd.read_csv(ARCHIVO))
        d.update({"id": "imagen_dirigentes", "nombre": "Imagen de dirigentes políticos", "seccion": "Opinión pública",
                  "fecha": date.today().isoformat(),
                  "nota": "Promedio simple de la última medición de cada encuestadora en los últimos 3 meses. Imagen positiva y negativa en % del total de encuestados (el resto no sabe o no conoce al dirigente). Cada encuestadora pregunta por un listado distinto, por eso no todos los dirigentes tienen la misma cantidad de mediciones. Arriba van los medidos por al menos dos encuestadoras."})
        (salida / "encuestas_imagen.json").write_text(json.dumps(d, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        return construir_problemas(salida)
    except Exception as e:
        return [f"Encuestas (imagen): {e}"]
