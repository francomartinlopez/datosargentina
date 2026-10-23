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

IDS = [
    "448.1_NIVEL_GENERAL_0_0_13_46", "456.1_VENTAS_PREADA_0_M_44_40", "458.1_VENTAS_TOTADA_0_M_52_56",
    "82.2_ITI_2004_T_27", "452.2_JUBILACIONVAS_0_T_36_18", "452.2_ENERGIAGIA_0_T_7_56",
    "452.2_TRANSFERENIAL_0_T_53_66", "151.1_AARIADODAD_2012_M_31", "186.3_TOTAL_POLISOS_0_0_23",
    "186.3_ASIGNACIONIAL_0_0_43", "189.1_TOTAL_AUHAUH_0_0_9", "165.1_AAUH_0_0_3",
    "75.3_IETPP_0_M_43", "75.3_ITMOA_0_M_13", "75.3_ITM_0_M_13", "75.3_ITCE_0_M_30", "74.3_IICL_0_M_42",
    "166.2_F_BRUTAIJO_0_0_19", "186.3_PENSIONES_VAS_0_0_26", "452.3_RESULTADO_ERO_0_M_20_25",
    "453.1_SERIE_ORIGNAL_0_0_14_46", "33.2_ISAC_NIVELRAL_0_M_18_63", "143.3_NO_PR_2004_A_21",
    "372.9_GTOS_CAP_T017__50_32", "452.3_PROGRAMA_IIAS_0_M_33_38",
]
BUSQUEDAS = [
    "capacidad instalada nivel general", "indice confianza consumidor", "tarjeta alimentar",
    "potenciar trabajo", "pensiones no contributivas beneficiarios", "gasto primario sector publico nacional",
    "gastos de capital sector publico nacional", "patentamientos", "producción de petróleo",
    "producción de gas natural", "empleo público", "índice de salarios", "canasta básica total",
    "pobreza", "turistas", "consumo de carne vacuna", "producción de leche", "escrituras",
    "despachos de cemento", "producción de acero", "índice de contratos de locación",
]
ARGENTINADATOS = [
    "cotizaciones/dolares/tarjeta", "cotizaciones/dolares/oficial", "cotizaciones/dolares/blue",
    "finanzas/indices/inflacion", "finanzas/tasas/plazoFijo", "finanzas/fci/mercadoDinero/ultimo",
    "finanzas/rendimientos",
]


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
        r = requests.get(BUSCAR, params={"q": q, "limit": 12}, headers=CAB, timeout=60)
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
    (SALIDA / "ids.json").write_text(json.dumps([sondear_id(i) for i in IDS], ensure_ascii=False, indent=1), encoding="utf-8")
    (SALIDA / "busquedas.json").write_text(json.dumps({q: buscar(q) for q in BUSQUEDAS}, ensure_ascii=False, indent=1), encoding="utf-8")
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
