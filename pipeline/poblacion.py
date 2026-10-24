"""Población según condición de actividad, a partir de los microdatos de la EPH (caché que arma
pipeline.fuentes.archivos.eph_tabla). Salida: sitio/public/datos/poblacion_actividad.json
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from .fuentes.archivos import EPH_CACHE

GRUPOS = [
    ("Población económicamente activa", [
        ("pob_ocupados_asal_registrados", "Asalariados formales (con aportes)"),
        ("pob_ocupados_asal_no_registrados", "Asalariados informales (sin aportes)"),
        ("pob_ocupados_cuenta_propia", "Cuenta propia (monotributistas y cuentapropistas)"),
        ("pob_ocupados_patrones", "Patrones y empleadores"),
        ("pob_ocupados_familiares", "Trabajadores familiares sin salario"),
        ("pob_desocupados", "Desocupados (buscan trabajo)"),
    ]),
    ("Fuera de la población activa", [
        ("pob_menores_10", "Menores de 10 años"),
        ("pob_inactivos_estudiantes", "Estudiantes"),
        ("pob_inactivos_jubilados", "Jubilados y pensionados"),
        ("pob_inactivos_amas_casa", "Amas y amos de casa"),
        ("pob_inactivos_discapacidad", "Personas con discapacidad"),
        ("pob_inactivos_rentistas", "Rentistas"),
        ("pob_inactivos_otros", "Otros (no trabajan ni buscan por otros motivos)"),
    ]),
]


def construir(salida: Path) -> list[str]:
    try:
        t = pd.read_csv(EPH_CACHE, dtype={"trimestre": str}).sort_values("trimestre")
        if "pob_total" not in t.columns:
            return ["Población por actividad: el caché de la EPH no tiene conteos"]
        t = t.dropna(subset=["pob_total"])
        d = {"id": "poblacion_actividad", "nombre": "Cómo se compone la población: quiénes trabajan, buscan o están fuera del mercado laboral",
             "seccion": "Empleo e ingresos", "fecha": date.today().isoformat(),
             "trimestres": t["trimestre"].tolist(), "total": [int(x) for x in t["pob_total"]],
             "grupos": [{"nombre": g, "categorias": [{"clave": c, "nombre": n, "valores": [int(x) for x in t[c].fillna(0)]} for c, n in cats]}
                        for g, cats in GRUPOS],
             "nota": "Microdatos de la Encuesta Permanente de Hogares (INDEC), 31 aglomerados urbanos: unos 29 millones de personas, dos tercios de la población del país. Cálculo propio con el factor de expansión de la encuesta. Asalariados formales e informales según tengan o no descuento jubilatorio. Cuenta propia junta a monotributistas y cuentapropistas sin registrar porque la encuesta no les pregunta si aportan. Quien no trabaja ni busca trabajo es inactivo, aunque quiera trabajar. Los inactivos se clasifican según cómo se declaran (por ejemplo, un jubilado que estudia figura como jubilado). Los menores de 10 años no responden las preguntas laborales. Hay estacionalidad entre trimestres: para ver cambios conviene comparar con el mismo trimestre de otro año."}
        (salida / "poblacion_actividad.json").write_text(json.dumps(d, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        return []
    except FileNotFoundError:
        return ["Población por actividad: no hay caché de la EPH"]
    except Exception as e:
        return [f"Población por actividad: {e}"]
