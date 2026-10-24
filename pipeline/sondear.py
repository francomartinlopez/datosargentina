"""Exploración: verifica IDs candidatos antes de sumarlos al catálogo.

- datos.gob.ar: pide cada ID y anota título, unidad, frecuencia, primer y último dato.
- datos.gob.ar: búsquedas por texto para los indicadores sin ID.
- BCRA v4: lista completa de variables con su descripción.
- ArgentinaDatos: prueba los endpoints candidatos.

Salida en data/sondeo/ (se guarda en la rama "exploracion").
"""
from __future__ import annotations

import json
import traceback
from pathlib import Path

import pandas as pd
import requests

from .fuentes import bcra

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "data" / "sondeo"
SERIES = "https://apis.datos.gob.ar/series/api/series/"
BUSCAR = "https://apis.datos.gob.ar/series/api/search/"
CAB = {"User-Agent": "datos-argentina/1.0 (github.com/francomartinlopez/datosargentina)"}

IDS = []
ARGENTINADATOS = ["finanzas/fci/mercadoDinero/penultimo", "finanzas/fci/mercadoDinero/2026/09/30", "finanzas/fci/rentaFija/ultimo"]
BUSQUEDAS = ['producción de soja', 'producción de maíz', 'producción de trigo', 'producción de girasol', 'estimaciones agrícolas producción', 'índice construya']


def sondear_id(i: str) -> dict:
    try:
        r = requests.get(SERIES, params={"ids": i, "format": "json", "limit": 1, "metadata": "full", "sort": "desc"}, headers=CAB, timeout=60)
        if r.status_code != 200:
            return {"id": i, "ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        j = r.json()
        meta = j["meta"][1] if len(j.get("meta", [])) > 1 else {}
        ser, dist, ds = meta.get("field", {}), meta.get("distribution", {}), meta.get("dataset", {})
        return {"id": i, "ok": True, "titulo": ser.get("description") or ser.get("title"), "unidad": ser.get("units"),
                "frecuencia": ser.get("frequency") or meta.get("frequency"), "inicio": ser.get("time_index_start"),
                "fin": ser.get("time_index_end"), "ultimo_valor": j["data"][0] if j.get("data") else None,
                "dataset": ds.get("title"), "distribucion": dist.get("title")}
    except Exception as e:
        return {"id": i, "ok": False, "error": repr(e)}


def buscar(q: str) -> list[dict]:
    try:
        r = requests.get(BUSCAR, params={"q": q, "limit": 25}, headers=CAB, timeout=60)
        out = []
        for x in r.json().get("data", []):
            f = x.get("field", {})
            out.append({"id": f.get("id"), "titulo": f.get("description") or f.get("title"), "unidad": f.get("units"),
                        "frecuencia": f.get("frequency"), "inicio": f.get("time_index_start"), "fin": f.get("time_index_end"),
                        "dataset": x.get("dataset", {}).get("title")})
        return out
    except Exception as e:
        return [{"error": repr(e)}]


def main() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    for i in IDS:
        try:
            r = requests.get(SERIES, params={"ids": i, "format": "csv", "limit": 5000}, headers=CAB, timeout=60)
            (SALIDA / f"serie_{i}.csv").write_text(r.text, encoding="utf-8")
        except Exception:
            pass
    (SALIDA / "ids.json").write_text(json.dumps([sondear_id(i) for i in IDS], ensure_ascii=False, indent=1), encoding="utf-8")
    resultados = {q: buscar(q) for q in BUSQUEDAS}
    # para cada resultado, verificar que la API devuelva valores (algunos IDs existen sin datos)
    for q, lista in resultados.items():
        for x in lista:
            if x.get("id"):
                x["ultimo_valor"] = sondear_id(x["id"]).get("ultimo_valor")
    (SALIDA / "busquedas.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        r = requests.get("https://api.bcra.gob.ar/estadisticas/v4.0/monetarias", headers=CAB, timeout=60, verify=bcra.VERIFICAR)
        filas = r.json().get("results", [])
        pd.DataFrame(filas).to_csv(SALIDA / "bcra_variables.csv", index=False)
    except Exception:
        (SALIDA / "bcra_error.txt").write_text(traceback.format_exc(), encoding="utf-8")
    ad = {}
    for e in ARGENTINADATOS:
        try:
            r = requests.get("https://api.argentinadatos.com/v1/" + e, headers=CAB, timeout=60)
            j = r.json()
            ad[e] = {"status": r.status_code, "n": len(j) if isinstance(j, list) else None,
                     "primero": j[0] if isinstance(j, list) and j else j if isinstance(j, dict) else None,
                     "ultimo": j[-1] if isinstance(j, list) and j else None}
        except Exception as ex:
            ad[e] = {"error": repr(ex)}
    (SALIDA / "argentinadatos.json").write_text(json.dumps(ad, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        SALIDA.mkdir(parents=True, exist_ok=True)
        (SALIDA / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        print(traceback.format_exc())
