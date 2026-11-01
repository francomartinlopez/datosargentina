import requests, pathlib, re, io
import pandas as pd
out = []
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
for f in ["informacion_mensual_2019.xlsx", "informacion_mensual_2023.xlsx"]:
    c = requests.get("https://www.argentina.gob.ar/sites/default/files/" + f, headers=H, timeout=90).content
    df = pd.read_excel(io.BytesIO(c), sheet_name="IIBB", header=None)
    for i in range(len(df)):
        t = str(df.iat[i, 1])
        if any(k in t.upper() for k in ["CORRIENTES", "SANTIAGO", "PAMPA", "JURISD"]):
            out.append(f"{f} r{i}: " + " | ".join(repr(x)[:14] for x in df.iloc[i, :15].tolist()))
c = requests.get("https://contenidos.afip.gob.ar/institucional/estudios/archivos/serie2014.xls", headers=H, timeout=90).content
df = pd.read_excel(io.BytesIO(c), header=None, sheet_name=0)
for i in range(3, 6):
    out.append("2014 r%d: " % i + " | ".join(repr(x)[:14] for x in df.iloc[i, :15].tolist()))
pathlib.Path("data/sondeo_recaudacion.txt").write_text("\n".join(out)); print("\n".join(out))
