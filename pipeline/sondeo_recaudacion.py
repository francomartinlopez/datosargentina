import requests, pathlib, re, io
import pandas as pd
out = []
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
def links(u):
    p = requests.get(u, headers=H, timeout=60)
    return p.status_code, sorted(set(re.findall(r'href="([^"]+\.(?:xlsx?|csv|zip))"', p.text, re.I)))
for u in ["https://www.afip.gob.ar/institucional/estudios/recaudacion-mensual/", "https://www.afip.gob.ar/institucional/estudios/serie-anual/",
          "https://www.argentina.gob.ar/economia/sechacienda/coordinacion-fiscal-provincial/recursos-tributarios-de-origen-provincial-top",
          "https://www.argentina.gob.ar/economia/sechacienda/asuntosprovinciales/direccion-de-recursos-provinciales/ingresos-brutos",
          "https://www.argentina.gob.ar/economia/sechacienda/asuntosprovinciales/recursos-provinciales"]:
    try:
        st, l = links(u); out.append(f"PAGE {u} {st} n={len(l)}\n  " + "\n  ".join(l[:15]) + ("\n  ...\n  " + "\n  ".join(l[-10:]) if len(l) > 15 else ""))
    except Exception as e:
        out.append(f"PAGE {u} ERR {e}")
def dump(url, nfilas=60):
    c = requests.get(url, headers=H, timeout=90).content
    h = pd.read_excel(io.BytesIO(c), sheet_name=None, header=None)
    out.append(f"FILE {url} sheets={list(h)[:30]}")
    for name, df in list(h.items())[:2]:
        out.append(f" SHEET {name} shape={df.shape}")
        for i in range(min(nfilas, len(df))):
            fila = [str(x)[:22] for x in df.iloc[i, :8].tolist()]
            if any(x != "nan" for x in fila): out.append("   " + " | ".join(fila))
try: dump("https://contenidos.afip.gob.ar/institucional/estudios/archivos/serie2026.xls", 90)
except Exception as e: out.append(f"ERR serie {e}")
pathlib.Path("data/sondeo_recaudacion.txt").write_text("\n".join(out)); print("\n".join(out))
