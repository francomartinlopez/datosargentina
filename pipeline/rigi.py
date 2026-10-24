"""Proyectos aprobados en el Régimen de Incentivo para Grandes Inversiones (RIGI).

Fuente: planilla pública que alimenta la web oficial del Ministerio de Economía
(argentina.gob.ar/economia/rigi). Un proyecto compartido entre provincias aparece una vez por
provincia: acá se cuenta una sola vez, con todas sus provincias.
Salida: sitio/public/datos/rigi.json
"""
from __future__ import annotations

import io
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd

from .fuentes import pedir

PAGINA = "https://www.argentina.gob.ar/economia/rigi"
DIVISAS = Path(__file__).resolve().parents[1] / "data" / "manual" / "rigi_divisas_bcra.csv"
NOMBRES_SECTOR = {"energia": "Energía eléctrica", "petroleo": "Petróleo y gas", "mineria": "Minería", "siderurgia": "Siderurgia", "infra": "Infraestructura"}
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


def plan_anual(html_pagina: str) -> list[dict]:
    """Cronograma anual de inversión de los proyectos aprobados (millones de US$), publicado en la web
    oficial como JSON dentro de la página."""
    import html as html_mod
    m = re.search(r'id="raw-data-json"[^>]*>(.*?)</div>\s*</div>', html_pagina, re.S)
    if not m:
        return []
    texto = html_mod.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
    filas = []
    for r in json.loads(texto):
        sectores = {NOMBRES_SECTOR.get(k, k): float(v["total"] if isinstance(v, dict) else v) for k, v in r.items() if k != "year"}
        filas.append({"anio": int(str(r["year"])[:4]), "total": round(sum(sectores.values())), "sectores": sectores})
    return sorted(filas, key=lambda f: f["anio"])


def ejecucion_estimada(plan: list[dict], hoy: date) -> dict | None:
    """Inversión que debería estar ejecutada según el cronograma: años cerrados completos más la parte
    proporcional del año en curso."""
    if not plan:
        return None
    cerrados = sum(f["total"] for f in plan if f["anio"] < hoy.year)
    actual = next((f["total"] for f in plan if f["anio"] == hoy.year), 0)
    return {"monto": round(cerrados + actual * (hoy.month - 1) / 12), "hasta": hoy.replace(day=1).isoformat(),
            "anios_cerrados": cerrados, "total_plan": round(sum(f["total"] for f in plan))}


def divisas_bcra() -> dict | None:
    try:
        df = pd.read_csv(DIVISAS)
        r = df.sort_values("fecha").iloc[-1]
        return {"fecha": r["fecha"], "neto": float(r["valor"]), "bruto": float(r["bruto"]), "egresos": float(r["egresos"]), "fuente": r["fuente_url"]}
    except Exception:
        return None


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
        try:
            plan = plan_anual(pedir(PAGINA).text)
        except Exception:
            plan = []
        d["plan_anual"] = plan
        d["ejecucion_estimada"] = ejecucion_estimada(plan, date.today())
        d["divisas_bcra"] = divisas_bcra()
        (salida / "rigi.json").write_text(json.dumps(d, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        return []
    except Exception as e:
        return [f"RIGI: {e}"]
