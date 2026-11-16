"""Prueba: panel interanual de la EPH (misma persona en t y t+4). Transiciones desde empleo formal e
informal y cambio de ingreso real. Resultado en data/sondeo_eph_panel.txt (no toca el sitio)."""
import io, zipfile, pathlib, time
import numpy as np
import pandas as pd
from pipeline.fuentes.archivos import _eph_zip
from pipeline import transformar

SAL = pathlib.Path("data/sondeo_eph_panel.txt")
log = []
def p(*a):
    t = " ".join(str(x) for x in a); print(t, flush=True); log.append(t)

COLS = ["CODUSU", "NRO_HOGAR", "COMPONENTE", "CH04", "CH06", "ESTADO", "CAT_OCUP", "PP07H", "P21", "PONDERA", "PONDIIO"]

def leer(anio, trim):
    c = _eph_zip(anio, trim)
    if c is None:
        return None, "sin zip"
    z = zipfile.ZipFile(io.BytesIO(c))
    nombres = [n for n in z.namelist() if ("individual" in n.lower() or "personas" in n.lower()) and n.lower().endswith((".txt", ".csv"))]
    if not nombres:
        return None, f"sin archivo de personas: {z.namelist()[:5]}"
    raw = z.open(nombres[0]).read()
    sep = ";" if raw[:2000].count(b";") > raw[:2000].count(b",") else ","
    df = pd.read_csv(io.BytesIO(raw), sep=sep, decimal=",", low_memory=False, encoding="latin-1",
                     usecols=lambda c: c.strip().upper() in COLS)
    df.columns = [c.strip().upper() for c in df.columns]
    falt = [c for c in COLS if c not in df.columns and c != "PONDIIO"]
    if falt:
        return None, f"faltan columnas {falt}"
    for c in df.columns:
        if c != "CODUSU":
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", "."), errors="coerce")
    df["CODUSU"] = df["CODUSU"].astype(str).str.strip()
    est, cat, ap = df["ESTADO"], df["CAT_OCUP"], df["PP07H"]
    s = pd.Series("X", index=df.index)
    s[(est == 1) & (cat == 3) & (ap == 1)] = "F"
    s[(est == 1) & (cat == 3) & (ap != 1)] = "I"
    s[(est == 1) & (cat == 2)] = "C"
    s[(est == 1) & cat.isin([1, 4])] = "O"
    s[est == 2] = "D"
    s[est == 3] = "N"
    df["sit"] = s
    df["w"] = df["PONDIIO"] if "PONDIIO" in df.columns and df["PONDIIO"].gt(0).any() else df["PONDERA"]
    return df[(df["CH06"] >= 18) & (df["CH06"] <= 64)], f"ok {len(df)} filas"

# deflactor: IPC empalmado del sitio, promedio trimestral
cr = lambda n: pd.read_csv(f"data/crudos/{n}.csv", parse_dates=["fecha"]).set_index("fecha")["valor"]
ipc = transformar.empalmar([(cr("ipc_gba_historico"), "2006-12-01"), (cr("ipc_san_luis"), "2012-07-01"), (cr("ipc_caba_2012"), "2016-12-01"), (cr("ipc_nacional"), None)])
ipc_t = ipc.groupby([ipc.index.year, (ipc.index.month - 1) // 3 + 1]).mean()

trims = [(a, t) for a in range(2003, 2027) for t in range(1, 5) if (a, t) >= (2003, 3)]
bases, t0 = {}, time.time()
for a, t in trims:
    df, msg = leer(a, t)
    if df is not None:
        bases[(a, t)] = df
    p(f"base {a}-T{t}: {msg}")
p(f"bases leídas: {len(bases)} en {time.time()-t0:.0f}s")

def wmed(x, w):
    o = np.argsort(x); x, w = np.asarray(x)[o], np.asarray(w)[o]; c = np.cumsum(w)
    return float(x[np.searchsorted(c, c[-1] / 2)])

filas = []
for (a, t), d0 in bases.items():
    d1 = bases.get((a + 1, t))
    if d1 is None:
        continue
    k = ["CODUSU", "NRO_HOGAR", "COMPONENTE"]
    m = d0.merge(d1, on=k, suffixes=("_0", "_1"))
    m = m[(m["CH04_0"] == m["CH04_1"]) & ((m["CH06_1"] - m["CH06_0"]).between(0, 2))]
    defl = ipc_t.get((a + 1, t)) / ipc_t.get((a, t))
    fila = {"trim": f"{a}-T{t}", "pares": len(m), "match_pct": round(100 * len(m) / max(1, len(d0)), 1)}
    for org in "FI":
        o = m[m["sit_0"] == org]
        fila[f"n_{org}"] = len(o)
        tot = o["w_0"].sum()
        for dst in "FICODN":
            fila[f"{org}>{dst}"] = round(100 * o.loc[o["sit_1"] == dst, "w_0"].sum() / tot, 1) if tot else None
    for org, dst in [("F", "F"), ("F", "I"), ("F", "C"), ("I", "F"), ("I", "I")]:
        o = m[(m["sit_0"] == org) & (m["sit_1"] == dst) & (m["P21_0"] > 0) & (m["P21_1"] > 0)]
        fila[f"n_ing_{org}{dst}"] = len(o)
        if len(o) >= 10 and defl:
            w = o["w_0"]
            fila[f"media_{org}{dst}"] = round(100 * (np.average(o["P21_1"], weights=w) / defl / np.average(o["P21_0"], weights=w) - 1), 1)
            fila[f"mediana_{org}{dst}"] = round(100 * (np.exp(wmed(np.log(o["P21_1"] / defl / o["P21_0"]), w)) - 1), 1)
    filas.append(fila)
r = pd.DataFrame(filas)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60); pd.set_option("display.max_rows", 200)
p("\n=== POR TRIMESTRE (t → t+4) ===")
p(r[["trim", "pares", "match_pct", "n_F", "F>F", "F>I", "F>C", "F>D", "F>N", "n_I", "I>F", "I>I", "I>C", "I>D", "I>N"]].to_string(index=False))
p("\n=== INGRESO REAL (% de cambio), casos por transición ===")
cols = ["trim"] + [c for c in r.columns if c.startswith(("n_ing", "media", "mediana"))]
p(r[cols].to_string(index=False))
r["anio"] = r["trim"].str[:4]
p("\n=== PROMEDIO ANUAL (por año del trimestre inicial) ===")
num = [c for c in r.columns if c not in ("trim", "anio")]
p(r.groupby("anio")[num].mean().round(1)[["pares", "n_F", "F>F", "F>I", "F>C", "F>D", "F>N", "n_I", "I>F", "I>I", "I>C", "n_ing_FI", "media_FI", "mediana_FI", "n_ing_FC", "media_FC", "mediana_FC", "n_ing_IF", "media_IF", "mediana_IF", "media_FF", "mediana_FF"]].to_string())
SAL.write_text("\n".join(log), encoding="utf-8")
