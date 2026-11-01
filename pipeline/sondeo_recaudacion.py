import requests, pathlib, re, io
import pandas as pd
out = []
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
A = "https://contenidos.afip.gob.ar/institucional/estudios/archivos/serie{}.xls"
for y in [2003, 2008, 2013, 2018, 2023, 2026]:
    try:
        c = requests.get(A.format(y), headers=H, timeout=90).content
        df = pd.read_excel(io.BytesIO(c), header=None, sheet_name=0)
        labs = [str(x).strip() for x in df.iloc[:, 1].tolist() if str(x) != "nan"]
        hdr = [str(x) for x in df.iloc[3].tolist()]
        out.append(f"Y{y} shape={df.shape} hdr={hdr}\n  " + " || ".join(labs[:60]))
    except Exception as e:
        out.append(f"Y{y} ERR {e}")
B = "https://www.argentina.gob.ar/sites/default/files/{}_ib.xlsx"
for y in range(2010, 2027):
    r = requests.get(B.format(y), headers=H, timeout=60)
    out.append(f"IB {y} {r.status_code} {len(r.content)} {r.content[:4]}")
c = requests.get(B.format(2025), headers=H, timeout=60).content
h = pd.read_excel(io.BytesIO(c), sheet_name=None, header=None)
out.append(f"IB2025 sheets={list(h)}")
for name, df in list(h.items())[:3]:
    out.append(f" SHEET {name} shape={df.shape}")
    for i in range(min(40, len(df))):
        fila = [str(x)[:18] for x in df.iloc[i, :16].tolist()]
        if any(x != "nan" for x in fila): out.append("   " + " | ".join(fila))
pathlib.Path("data/sondeo_recaudacion.txt").write_text("\n".join(out)); print("\n".join(out))
