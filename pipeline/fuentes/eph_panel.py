"""Panel interanual de la EPH: la misma persona en el trimestre t y un año después (t+4).

La EPH entrevista cada vivienda en dos trimestres seguidos, la deja descansar dos y la vuelve a
entrevistar dos más: la mitad de la muestra reaparece un año después. Con CODUSU + NRO_HOGAR +
COMPONENTE (y control de sexo y edad) se sigue a cada persona de 18 a 64 años y se mide:

- adónde va un año después quien era asalariado formal (con descuento jubilatorio) o informal:
  sigue igual, pasa al otro tipo de empleo asalariado, a cuenta propia, a la desocupación o a la
  inactividad (% ponderado);
- cuánto cambia su ingreso de la ocupación principal (P21) en cada transición: cociente de las
  medias y mediana de los cocientes individuales, ambos nominales (se deflactan al leer).

Bases: 2016-T2 en adelante en texto (.zip); 2003-T3 a 2015-T2 en Stata dentro de .zip o .rar.
Los resultados de cada par se guardan en data/derivados/eph_panel.csv y en cada corrida se
calculan solo los pares nuevos.
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
import zipfile
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from . import CABECERAS, TIMEOUT

EPH = "https://www.indec.gob.ar/ftp/cuadros/menusuperior/eph/"
CACHE = Path(__file__).resolve().parents[2] / "data" / "derivados" / "eph_panel.csv"
COLS = ["CODUSU", "NRO_HOGAR", "COMPONENTE", "CH04", "CH06", "ESTADO", "CAT_OCUP", "PP07H", "P21", "PONDERA", "PONDIIO"]
DESDE = (2003, 3)
ORIGENES = "FI"
DESTINOS = "FICODN"   # formal, informal, cuenta propia, otros ocupados, desocupado, inactivo
TRANSICIONES_INGRESO = ["FF", "FI", "FC", "IF", "II"]
MINIMO_CASOS = 10


# ---------- lectura de una base ----------

def _bajar(nombre: str) -> bytes | None:
    try:
        r = requests.get(EPH + nombre, headers=CABECERAS, timeout=TIMEOUT)
    except requests.RequestException:
        return None
    return r.content if r.status_code == 200 and len(r.content) > 1000 else None


def _extraer(contenido: bytes, ext: str) -> list[str]:
    """Descomprime .zip o .rar en una carpeta temporal y devuelve los archivos."""
    d = tempfile.mkdtemp()
    if ext == "zip":
        zipfile.ZipFile(io.BytesIO(contenido)).extractall(d)
    else:
        arch = os.path.join(d, "base.rar")
        Path(arch).write_bytes(contenido)
        for cmd in (["7z", "x", "-y", f"-o{d}", arch], ["unar", "-q", "-o", d, arch], ["bsdtar", "-xf", arch, "-C", d]):
            if shutil.which(cmd[0]):
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                if any(f.lower().endswith((".dta", ".txt")) for _, _, fs in os.walk(d) for f in fs):
                    break
    return [os.path.join(rt, f) for rt, _, fs in os.walk(d) for f in fs]


def _es_personas(nombre: str) -> bool:
    n = os.path.basename(nombre).lower()
    return any(k in n for k in ("individual", "personas", "ind_", "_ind", "indiv")) or n.startswith("ind")


def leer_base(anio: int, trim: int) -> pd.DataFrame | None:
    if (anio, trim) < (2016, 2):
        base = f"t{trim}{str(anio)[2:]}_dta"
        for ext in ("zip", "rar"):
            c = _bajar(f"{base}.{ext}")
            if c:
                archivos = [f for f in _extraer(c, ext) if f.lower().endswith(".dta") and _es_personas(f)]
                if archivos:
                    df = pd.read_stata(archivos[0], convert_categoricals=False)
                    df.columns = [str(x).strip().upper() for x in df.columns]
                    return preparar(df[[x for x in COLS if x in df.columns]])
        return None
    from .archivos import _eph_zip
    c = _eph_zip(anio, trim)
    if c is None:
        return None
    z = zipfile.ZipFile(io.BytesIO(c))
    nombres = [n for n in z.namelist() if _es_personas(n) and n.lower().endswith((".txt", ".csv"))]
    if not nombres:
        return None
    crudo = z.open(nombres[0]).read()
    sep = ";" if crudo[:2000].count(b";") > crudo[:2000].count(b",") else ","
    df = pd.read_csv(io.BytesIO(crudo), sep=sep, decimal=",", low_memory=False, encoding="latin-1",
                     usecols=lambda x: x.strip().upper() in COLS)
    df.columns = [x.strip().upper() for x in df.columns]
    return preparar(df)


def preparar(df: pd.DataFrame) -> pd.DataFrame:
    faltan = [c for c in COLS if c not in df.columns and c != "PONDIIO"]
    if faltan:
        raise ValueError(f"EPH: faltan columnas {faltan}")
    df = df.copy()
    for c in df.columns:
        if c != "CODUSU":
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", "."), errors="coerce")
    df["CODUSU"] = df["CODUSU"].astype(str).str.strip()
    df["P21"] = df["P21"].where(df["P21"] > 0)
    est, cat, aporta = df["ESTADO"], df["CAT_OCUP"], df["PP07H"]
    sit = pd.Series("X", index=df.index)
    sit[(est == 1) & (cat == 3) & (aporta == 1)] = "F"
    sit[(est == 1) & (cat == 3) & (aporta != 1)] = "I"
    sit[(est == 1) & (cat == 2)] = "C"
    sit[(est == 1) & cat.isin([1, 4])] = "O"
    sit[est == 2] = "D"
    sit[est == 3] = "N"
    df["sit"] = sit
    pondiio = df["PONDIIO"] if "PONDIIO" in df.columns else None
    df["w"] = pondiio if pondiio is not None and pondiio.gt(0).any() else df["PONDERA"]
    return df[(df["CH06"] >= 18) & (df["CH06"] <= 64)]


# ---------- un par t -> t+4 ----------

def _mediana_ponderada(x, w) -> float:
    x, w = np.asarray(x, float), np.asarray(w, float)
    o = np.argsort(x)
    x, w = x[o], w[o]
    c = np.cumsum(w)
    return float(x[np.searchsorted(c, c[-1] / 2)])


def resumir_par(d0: pd.DataFrame, d1: pd.DataFrame) -> dict:
    claves = ["CODUSU", "NRO_HOGAR", "COMPONENTE"]
    m = d0.merge(d1, on=claves, suffixes=("_0", "_1"))
    m = m[(m["CH04_0"] == m["CH04_1"]) & (m["CH06_1"] - m["CH06_0"]).between(0, 2)]
    fila = {"pares": int(len(m))}
    for org in ORIGENES:
        o = m[m["sit_0"] == org]
        tot = o["w_0"].sum()
        fila[f"n_{org}"] = int(len(o))
        for dst in DESTINOS:
            fila[f"{org}>{dst}"] = 100 * o.loc[o["sit_1"] == dst, "w_0"].sum() / tot if tot else None
    for tr in TRANSICIONES_INGRESO:
        o = m[(m["sit_0"] == tr[0]) & (m["sit_1"] == tr[1]) & m["P21_0"].notna() & m["P21_1"].notna()]
        fila[f"n_ing_{tr}"] = int(len(o))
        if len(o) >= MINIMO_CASOS:
            w = o["w_0"]
            fila[f"media_nom_{tr}"] = float(np.average(o["P21_1"], weights=w) / np.average(o["P21_0"], weights=w))
            fila[f"mediana_nom_{tr}"] = float(np.exp(_mediana_ponderada(np.log(o["P21_1"] / o["P21_0"]), w)))
    return fila


# ---------- tabla con caché ----------

def _siguiente(a: int, t: int) -> tuple[int, int]:
    return (a + 1, 1) if t == 4 else (a, t + 1)


@lru_cache(maxsize=None)
def tabla() -> pd.DataFrame:
    previo = pd.read_csv(CACHE, dtype={"trimestre": str}) if CACHE.exists() else pd.DataFrame(columns=["trimestre"])
    hechos = set(previo["trimestre"])
    hoy = pd.Timestamp.today()
    bases: dict = {}

    def base(a, t):
        if (a, t) not in bases:
            try:
                bases[(a, t)] = leer_base(a, t)
            except Exception:
                bases[(a, t)] = None
        return bases[(a, t)]

    nuevos, (a, t) = [], DESDE
    while (a + 1, t) <= (hoy.year, (hoy.month - 1) // 3 + 1):
        clave = f"{a}-T{t}"
        if clave not in hechos:
            d1 = base(a + 1, t)           # primero la del año siguiente: si no existe, no se baja la otra
            d0 = base(a, t) if d1 is not None else None
            if d0 is not None and d1 is not None:
                nuevos.append({"trimestre": clave, **resumir_par(d0, d1)})
            bases.pop((a, t), None)       # libera memoria: la base de t ya no se usa como t+4
        a, t = _siguiente(a, t)
    t_ = pd.concat([previo, pd.DataFrame(nuevos)], ignore_index=True) if nuevos else previo
    if nuevos:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        t_.sort_values("trimestre").to_csv(CACHE, index=False)
    return t_


# ---------- series para el sitio ----------

def _deflactor_trimestral() -> pd.Series:
    """IPC empalmado del sitio (crudos guardados), con un mes de rezago: P21 es el ingreso del mes
    anterior a la entrevista. Promedio por trimestre."""
    from .. import transformar
    base = Path(__file__).resolve().parents[2] / "data" / "crudos"
    cr = lambda n: pd.read_csv(base / f"{n}.csv", parse_dates=["fecha"]).set_index("fecha")["valor"]
    ipc = transformar.empalmar([(cr("ipc_gba_historico"), "2006-12-01"), (cr("ipc_san_luis"), "2012-07-01"),
                                (cr("ipc_caba_2012"), "2016-12-01"), (cr("ipc_nacional"), None)]).shift(1)
    trim = ipc.groupby(ipc.index.to_period("Q")).agg(["mean", "count"])
    return trim.loc[trim["count"] == 3, "mean"]


def serie(campo: str, ventana: int = 4) -> pd.Series:
    """campo: 'F>I' (% de los formales que un año después son informales), 'mediana_FI' o 'media_FI'
    (% de cambio real del ingreso). Fecha: trimestre en que termina el año observado (t+4).
    Promedio móvil de `ventana` trimestres; un hueco corta el promedio."""
    t = tabla()
    inicio = pd.PeriodIndex(t["trimestre"].str.replace("-T", "Q"), freq="Q")
    fin = inicio + 4
    if campo.startswith(("media_", "mediana_")):
        medida, tr = campo.split("_")
        nominal = pd.to_numeric(t.get(f"{medida}_nom_{tr}"), errors="coerce").to_numpy()
        defl = _deflactor_trimestral()
        d = np.array([defl.get(f, np.nan) / defl.get(i, np.nan) for i, f in zip(inicio, fin)])
        valores = (nominal / d - 1) * 100
    else:
        valores = pd.to_numeric(t[campo], errors="coerce").to_numpy()
    s = pd.Series(valores, index=fin).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    s = s.reindex(pd.period_range(s.index.min(), s.index.max(), freq="Q"))
    s = s.rolling(ventana, min_periods=ventana).mean().dropna()
    s.index = s.index.to_timestamp()
    return s
