import requests, pathlib, re, io
import pandas as pd
out = []
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
A = "https://contenidos.afip.gob.ar/institucional/estudios/archivos/serie{}.xls"
for y in [2003, 2005, 2007]:
    c = requests.get(A.format(y), headers=H, timeout=90).content
    df = pd.read_excel(io.BytesIO(c), header=None, sheet_name=0)
    for i in range(min(12, len(df))):
        out.append(f"Y{y} r{i}: " + " | ".join(str(x)[:20] for x in df.iloc[i, :5].tolist()))
    labs = [str(x).strip() for x in df.iloc[:, 0].tolist() if str(x) != "nan"]
    out.append(f"Y{y} col0: " + " || ".join(labs[:70]))
u = "https://www.argentina.gob.ar/economia/sechacienda/asuntosprovinciales/direccion-de-recursos-provinciales/recursos-tributarios-de-origen-provincial-top"
p = requests.get(u, headers=H, timeout=60).text
files = sorted(set(re.findall(r'/sites/default/files/((?:top_mensual|informacion_mensual)_[^"]+\.xlsx)', p)))
out.append("MENS " + str(files))
for f in files:
    c = requests.get("https://www.argentina.gob.ar/sites/default/files/" + f, headers=H, timeout=90).content
    h = pd.read_excel(io.BytesIO(c), sheet_name=None, header=None)
    k = [s for s in h if "IIBB" in s.upper() or "BRUTOS" in s.upper()]
    df = h[k[0]] if k else list(h.values())[0]
    txt = [" | ".join(str(x)[:30] for x in df.iloc[i, :4].tolist()) for i in range(6)]
    jur = [str(x).strip() for x in df.iloc[:, 1].tolist() if str(x) != "nan"]
    out.append(f"F {f} sheets={list(h)} hoja={k} shape={df.shape}\n   " + "\n   ".join(txt) + "\n   JUR " + " | ".join(jur[:40]))
pathlib.Path("data/sondeo_recaudacion.txt").write_text("\n".join(out)); print("\n".join(out))
