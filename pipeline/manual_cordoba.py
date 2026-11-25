"""Carga de datos de la Dirección General de Estadística y Censos de Córdoba (datosestadistica.cba.gov.ar).

El portal (CKAN) no responde a los servidores de GitHub, así que esta carga la corre la tarea
programada del día 20 desde una sesión de Claude y deja los CSV en data/manual/:
- ipc_cordoba.csv: IPC de la provincia, nivel general. Serie base 2014=100 (julio 2013 a noviembre
  2025) encadenada con la serie nueva (base junio-noviembre 2025) desde noviembre de 2025.
- expo_cordoba.csv y expo_cordoba_<rubro>.csv: exportaciones mensuales de bienes con origen en
  Córdoba, en millones de US$ FOB (total y por gran rubro).
- pgb_cordoba.csv: producto geográfico bruto, millones de pesos de 2004 (anual).

Uso: python -m pipeline.manual_cordoba
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import requests

API = "https://datosestadistica.cba.gov.ar/api/3/action/"
# el portal devuelve 404 a clientes que no se identifican como navegador
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"}
SALIDA = Path(__file__).resolve().parents[1] / "data" / "manual"
PORTAL = "https://datosestadistica.cba.gov.ar/dataset/"
MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12}
RUBROS = {"Productos primarios (PP)": "pp", "Manufacturas de origen agropecuario (MOA)": "moa",
          "Manufacturas de origen industrial (MOI)": "moi", "Combustibles y energía (CyE)": "cye"}


def numero(v) -> float | None:
    if v is None or str(v).strip() in ("", "-", "///"):
        return None
    return float(str(v).replace(".", "").replace(",", "."))


def recursos(conjunto: str) -> list[dict]:
    r = requests.get(API + "package_show", params={"id": conjunto}, headers=UA, timeout=60)
    r.raise_for_status()
    return r.json()["result"]["resources"]


def registros(resource_id: str) -> list[dict]:
    r = requests.get(API + "datastore_search", params={"resource_id": resource_id, "limit": 32000}, headers=UA, timeout=120)
    r.raise_for_status()
    return r.json()["result"]["records"]


def recurso(conjunto: str, condicion) -> dict:
    """El recurso CSV con datastore más reciente que cumple la condición sobre su nombre o URL."""
    cands = [r for r in recursos(conjunto) if (r.get("format") or "").upper() == "CSV" and r.get("datastore_active") and condicion(r)]
    if not cands:
        raise RuntimeError(f"Córdoba: no hay recurso en {conjunto}")
    return max(cands, key=lambda r: r.get("last_modified") or r.get("created") or "")


def fila_mensual(rec: dict) -> pd.Series:
    """Una fila con columnas 'mmm-aa' → serie mensual."""
    s = {}
    for k, v in rec.items():
        m = re.fullmatch(r"([a-z]{3})-(\d{2})", str(k).strip().lower())
        if m and m.group(1) in MESES and numero(v) is not None:
            s[pd.Timestamp(2000 + int(m.group(2)), MESES[m.group(1)], 1)] = numero(v)
    return pd.Series(s, dtype=float).sort_index()


def nivel_general(recs: list[dict]) -> pd.Series:
    for r in recs:
        if str(r.get("Descripcion", "")).strip().upper() == "NIVEL GENERAL" or str(r.get("NIVEL", "")).strip() == "0":
            return fila_mensual(r)
    raise RuntimeError("Córdoba: no está el nivel general del IPC")


def ipc() -> pd.Series:
    vieja = nivel_general(registros(recurso("indic", lambda r: "2014" in r["name"] and "empalme" not in r["name"].lower())["id"]))
    nueva = nivel_general(registros(recurso("indic", lambda r: r["name"].strip() == "IPC-CBA")["id"]))
    union = nueva.index.min()
    if union not in vieja.index:
        raise RuntimeError("Córdoba: las dos bases del IPC no se superponen")
    factor = vieja[union] / nueva[union]
    return pd.concat([vieja[vieja.index < union], nueva * factor]).sort_index()


def exportaciones() -> pd.DataFrame:
    recs = registros(recurso("comercio-exterior", lambda r: "mensual" in r["name"].lower())["id"])
    df = pd.DataFrame(recs)
    df = df[df["Mes"].notna() & df["Rubro"].notna()]
    df["fecha"] = pd.to_datetime(df["Ano"].astype(str).str.extract(r"(\d{4})")[0] + "-" + df["Mes"].astype(str).str.zfill(2) + "-01")
    df["v"] = df["FOB_dolar"].map(numero) / 1e6
    return df.pivot_table(index="fecha", columns="Rubro", values="v", aggfunc="sum").sort_index()


def pgb() -> pd.Series:
    recs = registros(recurso("pgb", lambda r: "2004" in r["url"] and "2015" not in r["url"])["id"])
    anios = {k: re.match(r"(\d{4})", str(v)).group(1) for k, v in recs[0].items() if v and re.match(r"\d{4}", str(v))}
    fila = next(r for r in recs if any(str(v).strip().upper().startswith("PRODUCTO GEOGR") for v in r.values())
                and any(numero(r[k]) for k in anios))
    return pd.Series({pd.Timestamp(int(a), 1, 1): numero(fila[k]) for k, a in anios.items()}, dtype=float).dropna().sort_index()


def guardar(nombre: str, s: pd.Series, fuente: str, decimales: int = 2) -> None:
    df = pd.DataFrame({"fecha": s.index.strftime("%Y-%m-%d"), "valor": s.round(decimales).values, "fuente_url": fuente})
    df.to_csv(SALIDA / f"{nombre}.csv", index=False)
    print(f"{nombre}: {len(df)} datos, {df['fecha'].iloc[0]} a {df['fecha'].iloc[-1]}")


def main() -> None:
    guardar("ipc_cordoba", ipc(), PORTAL + "indic (Dirección General de Estadística y Censos de Córdoba, IPC-CBA, nivel general; base 2014 encadenada con la base 2025)")
    e = exportaciones()
    fuente = PORTAL + "comercio-exterior (Dirección General de Estadística y Censos de Córdoba, exportaciones mensuales de bienes, con datos del INDEC)"
    guardar("expo_cordoba", e.sum(axis=1, min_count=1).dropna(), fuente, 1)
    for col, clave in RUBROS.items():
        if col in e.columns:
            guardar(f"expo_cordoba_{clave}", e[col].dropna(), fuente, 1)
    try:
        guardar("pgb_cordoba", pgb(), PORTAL + "pgb (Dirección General de Estadística y Censos de Córdoba, producto geográfico bruto a precios de 2004)", 0)
    except Exception as ex:  # el cuadro del PGB cambia de formato: no frena el resto
        print(f"PGB: {ex}")


if __name__ == "__main__":
    main()
