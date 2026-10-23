"""Pirámide de ingresos: deciles de ingreso per cápita familiar del último informe de la EPH.

INDEC agrupa los deciles en estratos: bajo (deciles 1 a 4), medio (5 a 8) y alto (9 y 10).
Se publican dos lecturas: deciles de personas (cuadro 1) y deciles de hogares (cuadro 9).

Salida: sitio/public/datos/distribucion_ingreso.json
"""
from __future__ import annotations

import json
from pathlib import Path

from .fuentes import archivos

ESTRATOS = [("Bajo", range(1, 5)), ("Medio", range(5, 9)), ("Alto", range(9, 11))]


def resumir(deciles: list[dict], clave_cantidad: str) -> list[dict]:
    out = []
    for nombre, rango in ESTRATOS:
        d = [x for x in deciles if x["decil"] in rango]
        cantidad = sum(x[clave_cantidad] for x in d)
        poblacion = sum(x["poblacion_miles"] for x in d)
        ingreso = sum(x["ingreso_total_millones"] for x in d)
        out.append({"estrato": nombre, "deciles": f"{rango.start} a {rango.stop - 1}" if rango.stop - rango.start > 2 else f"{rango.start} y {rango.stop - 1}", "cantidad_miles": round(cantidad, 1),
                    "poblacion_miles": round(poblacion, 1), "porcentaje_ingreso": round(sum(x["porcentaje_ingreso"] for x in d), 1),
                    # ingreso per cápita medio del estrato = ingreso total / población
                    "ingreso_medio": round(ingreso * 1e6 / (poblacion * 1e3)) if poblacion else None,
                    "desde": min(x["desde"] for x in d), "hasta": max(x["hasta"] for x in d)})
    return out


def construir(salida: Path) -> list[str]:
    try:
        d = archivos.indec_distribucion_ingreso()
        datos = {
            "id": "distribucion_ingreso",
            "nombre": "Pirámide de ingresos",
            "seccion": "Empleo e ingresos",
            "periodo": f"{['I', 'II', 'III', 'IV'][d['trimestre'] - 1]} trim. {d['anio']}" if d["trimestre"] else "",
            "fuente": "INDEC, Evolución de la distribución del ingreso (EPH), 31 aglomerados urbanos",
            "nota": "Ingreso per cápita familiar en pesos corrientes del trimestre. Estratos según INDEC: bajo (deciles 1 a 4), medio (5 a 8) y alto (9 y 10). Los hogares de menores ingresos tienen más integrantes, por eso un decil de hogares no reúne el 10% de las personas.",
            "personas": {"deciles": d["personas"], "estratos": resumir(d["personas"], "poblacion_miles")},
            "hogares": {"deciles": d["hogares"], "estratos": resumir(d["hogares"], "hogares_miles")},
        }
        (salida / "distribucion_ingreso.json").write_text(json.dumps(datos, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        return []
    except Exception as e:
        return [f"pirámide de ingresos: {e}"]
