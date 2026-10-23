"""Proyectos aprobados en el Régimen de Incentivo para Grandes Inversiones (RIGI).

Fuente: planilla pública que alimenta la web oficial del Ministerio de Economía
(argentina.gob.ar/economia/rigi). Un proyecto compartido entre provincias aparece una vez por
provincia: acá se cuenta una sola vez, con todas sus provincias.
Salida: sitio/public/datos/rigi.json
"""
from __future__ import annotations

import io
import json
from datetime import date
from pathlib import Path

import pandas as pd

from .fuentes import pedir

PLANILLA = "https://docs.google.com/spreadsheets/d/1eytHJrzUjIFOXI-P1Hx_wbmZiSqPxVle059Djdos6u8/gviz/tq?tqx=out:csv&sheet=dataset"


def proyectos(texto: str) -> list[dict]:
    df = pd.read_csv(io.StringIO(texto), dtype=str).fillna("")
    df = df[df["provincia"] != "Provincia"]  # segunda fila: encabezados legibles
    df["inv"] = pd.to_numeric(df["inv-comprometida"], errors="coerce")
    df["emp"] = pd.to_numeric(df["empleos-generados"], errors="coerce")
    df = df.dropna(subset=["inv"])
    df["empresa"] = df["empresa"].str.strip(" .\n")
    out = []
    for (nombre, empresa), g in df.groupby(["nombre", "empresa"], sort=False):
        provincias = sorted(set(g["provincia"]) | {p.strip() for c in g["compartido"] for p in c.split(",") if p.strip()})
        r = g.iloc[0]
        out.append({"nombre": nombre.strip(), "empresa": empresa, "provincias": provincias, "sector": r["sector"].strip(),
                    "inversion": float(r["inv"]), "empleos": int(r["emp"]) if pd.notna(r["emp"]) else None,
                    "descripcion": r["descripcion"].strip(), "norma": r["enlace"].strip()})
    return sorted(out, key=lambda p: -p["inversion"])


def construir(salida: Path) -> list[str]:
    try:
        lista = proyectos(pedir(PLANILLA).text)
        if not lista:
            raise ValueError("planilla vacía")
        sectores = {}
        for p in lista:
            s = sectores.setdefault(p["sector"], {"sector": p["sector"], "inversion": 0.0, "proyectos": 0})
            s["inversion"] += p["inversion"]; s["proyectos"] += 1
        d = {"id": "rigi", "nombre": "Proyectos aprobados en el RIGI", "seccion": "Sector externo e inversión",
             "fecha": date.today().isoformat(), "fuente": "Ministerio de Economía, web oficial del RIGI (argentina.gob.ar/economia/rigi)",
             "nota": "Inversión total comprometida por cada proyecto en millones de dólares corrientes, según su aprobación por el Comité Evaluador; es un compromiso a varios años, no inversión ya realizada. Los empleos son directos e indirectos estimados por las empresas.",
             "total_inversion": round(sum(p["inversion"] for p in lista)), "total_empleos": sum(p["empleos"] or 0 for p in lista),
             "sectores": sorted(sectores.values(), key=lambda s: -s["inversion"]), "proyectos": lista}
        (salida / "rigi.json").write_text(json.dumps(d, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        return []
    except Exception as e:
        return [f"RIGI: {e}"]
