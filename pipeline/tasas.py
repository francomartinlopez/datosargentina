"""Foto del día de las tasas en pesos: plazo fijo por banco y fondos de dinero (cuentas
remuneradas de las billeteras), a partir de ArgentinaDatos.

La TNA de cada fondo se calcula con la variación de la cuotaparte entre los dos últimos días
publicados. Salida: sitio/public/datos/tasas.json
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from .fuentes import pedir

BASE = "https://api.argentinadatos.com/v1/finanzas/"


def nombre_banco(n: str) -> str:
    n = re.sub(r"\s+", " ", n.strip().title())
    for a, b in ((" De La ", " de la "), (" De ", " de "), (" Del ", " del "), (" Y ", " y "), ("S.A.", ""), (" Sa", ""),
                 ("Banco de la Nacion Argentina", "Banco Nación"), ("Ciudad de Buenos Aires", "Ciudad"), ("Bbva", "BBVA"),
                 ("Icbc", "ICBC"), ("Hsbc", "HSBC"), ("Bica", "BICA")):
        n = n.replace(a, b)
    return n.strip(" .")


def plazo_fijo() -> list[dict]:
    filas = []
    for r in pedir(BASE + "tasas/plazoFijo").json():
        tna = r.get("tnaClientes")
        if tna:
            filas.append({"nombre": nombre_banco(r["entidad"]), "tna": round(float(tna) * 100, 2)})
    return sorted(filas, key=lambda f: -f["tna"])


def fondos(n: int = 12) -> tuple[list[dict], str]:
    u = pd.DataFrame(pedir(BASE + "fci/mercadoDinero/ultimo").json())
    p = pd.DataFrame(pedir(BASE + "fci/mercadoDinero/penultimo").json())
    fecha = u["fecha"].max()
    u = u[(u["fecha"] == fecha) & (u["patrimonio"] > 0)]
    df = u.merge(p[["fondo", "fecha", "vcp"]], on="fondo", suffixes=("", "_ant"))
    df["dias"] = (pd.to_datetime(df["fecha"]) - pd.to_datetime(df["fecha_ant"])).dt.days
    df = df[(df["dias"] > 0) & (df["dias"] <= 5) & (df["vcp_ant"] > 0)]
    df["tna"] = (df["vcp"] / df["vcp_ant"] - 1) * 365 / df["dias"] * 100
    df["base"] = df["fondo"].str.replace(r"\s*-\s*Clase.*$", "", regex=True).str.strip()
    # un renglón por fondo (la clase con más patrimonio) y tasas plausibles
    df = df[(df["tna"] > 0) & (df["tna"] < 200)].sort_values("patrimonio", ascending=False).drop_duplicates("base")
    top = df.head(n).sort_values("tna", ascending=False)
    return [{"nombre": r.base, "tna": round(float(r.tna), 2), "patrimonio_millones": round(float(r.patrimonio) / 1e6)} for r in top.itertuples()], fecha


def construir(salida: Path) -> list[str]:
    try:
        f, fecha = fondos()
        d = {"id": "tasas_hoy", "nombre": "Tasas en pesos hoy", "seccion": "Dólar y finanzas", "fecha": fecha,
             "fuente": "ArgentinaDatos (BCRA y Cámara Argentina de FCI)",
             "nota": "Foto del último día hábil, no una serie histórica. Los fondos de dinero no garantizan la tasa: es el rendimiento observado de un día anualizado.",
             "plazo_fijo": plazo_fijo(), "fondos": f}
        (salida / "tasas.json").write_text(json.dumps(d, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        return []
    except Exception as e:
        return [f"tasas de hoy: {e}"]
