import requests, pathlib, re, io
import pandas as pd
out = []
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
u = "https://www.argentina.gob.ar/economia/sechacienda/asuntosprovinciales/direccion-de-recursos-provinciales/recursos-tributarios-de-origen-provincial-top"
p = requests.get(u, headers=H, timeout=60)
out.append(f"{p.status_code} len={len(p.text)}")
hrefs = re.findall(r'href="([^"]+)"', p.text)
files = [h for h in hrefs if re.search(r'\.(xlsx?|csv|zip)', h, re.I)]
out.append("FILES " + "\n ".join(files))
def dump(url, n=45, cols=14):
    url = url if url.startswith("http") else "https://www.argentina.gob.ar" + url.replace("blank:#", "")
    c = requests.get(url, headers=H, timeout=90).content
    if c[:4] not in (b"PK\x03\x04", b"\xd0\xcf\x11\xe0"):
        out.append(f"NOFILE {url} {c[:60]}"); return
    h = pd.read_excel(io.BytesIO(c), sheet_name=None, header=None)
    out.append(f"FILE {url} sheets={list(h)[:40]}")
    for name, df in list(h.items())[:2]:
        out.append(f" SHEET {name} shape={df.shape}")
        for i in range(min(n, len(df))):
            fila = [str(x)[:16] for x in df.iloc[i, :cols].tolist()]
            if any(x != "nan" for x in fila): out.append("   " + " | ".join(fila))
mens = [f for f in files if "mens" in f.lower()]
for f in (mens[:1] + [f for f in files if "serie" in f.lower() or "top_" in f.lower()][:2]):
    try: dump(f)
    except Exception as e: out.append(f"ERR {f} {e}")
pathlib.Path("data/sondeo_recaudacion.txt").write_text("\n".join(out)); print("\n".join(out))
