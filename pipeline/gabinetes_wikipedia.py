"""Ministros y jefes de Gabinete desde 2003, a partir de los anexos de Wikipedia en español.

Fuente de trabajo para la serie de rotación de gabinete. Cada fila debe contrastarse con el
decreto de designación o de aceptación de renuncia del Boletín Oficial antes de publicarse.

Salida:
  data/gabinetes/ministros.csv   gestion, cartera, titular, inicio, fin
  data/gabinetes/resumen.csv     indicadores de rotación por gestión
"""
from __future__ import annotations

import io
import re
import time
import traceback
from pathlib import Path

import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "data" / "gabinetes"
API = "https://es.wikipedia.org/w/api.php"
CAB = {"User-Agent": "datos-argentina/1.0 (github.com/francomartinlopez/datosargentina; contacto via GitHub)"}

GESTIONES = {
    "Néstor Kirchner": ("Anexo:Gabinete de Ministros de Néstor Kirchner", "2003-05-25", "2007-12-10"),
    "Cristina Fernández de Kirchner": ("Anexo:Gabinete de Ministros de Cristina Fernández de Kirchner", "2007-12-10", "2015-12-10"),
    "Mauricio Macri": ("Anexo:Gabinete de Ministros de Mauricio Macri", "2015-12-10", "2019-12-10"),
    "Alberto Fernández": ("Anexo:Gabinete de Ministros de Alberto Fernández", "2019-12-10", "2023-12-10"),
    "Javier Milei": ("Anexo:Gabinete de Ministros de Javier Milei", "2023-12-10", None),
}
MESES = {m: i for i, m in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                                     "septiembre", "octubre", "noviembre", "diciembre"], 1)}


def fecha(texto) -> pd.Timestamp | None:
    if not isinstance(texto, str):
        return None
    t = re.sub(r"\[.*?\]", "", texto).lower()
    m = re.search(r"(\d{1,2}) de (\w+) de (\d{4})", t)
    if not m or m.group(2) not in MESES:
        return None
    return pd.Timestamp(int(m.group(3)), MESES[m.group(2)], int(m.group(1)))


def tablas(titulo: str) -> list[pd.DataFrame]:
    for intento in range(5):
        r = requests.get(API, params={"action": "parse", "page": titulo, "prop": "text", "format": "json",
                                      "formatversion": 2}, headers=CAB, timeout=60)
        if r.status_code == 429:
            time.sleep(10 * (intento + 1))
            continue
        r.raise_for_status()
        return pd.read_html(io.StringIO(r.json()["parse"]["text"]))
    raise RuntimeError(f"Wikipedia limitó los pedidos para {titulo}")


def normalizar(df: pd.DataFrame, gestion: str) -> pd.DataFrame:
    cols = {c: str(c) for c in df.columns}
    df = df.rename(columns=cols)
    cartera = next((c for c in df.columns if c.lower().startswith(("ministerio", "cartera", "cargo"))), df.columns[0])
    titulares = [c for c in df.columns if c.lower().startswith("titular")]
    inicio = next((c for c in df.columns if c.lower().startswith("inicio")), None)
    fin = next((c for c in df.columns if c.lower().startswith(("final", "fin"))), None)
    if not titulares or inicio is None:
        return pd.DataFrame()
    titular = df[titulares].astype(str).apply(lambda r: next((v for v in r[::-1] if v not in ("nan", "")), ""), axis=1)
    out = pd.DataFrame({
        "gestion": gestion,
        "cartera": df[cartera].astype(str).str.replace(r"\[.*?\]", "", regex=True).str.strip(),
        "titular": titular.str.replace(r"\[.*?\]", "", regex=True).str.strip(),
        "inicio": df[inicio].map(fecha),
        "fin": df[fin].map(fecha) if fin else None,
    })
    return out.dropna(subset=["inicio"]).drop_duplicates(subset=["cartera", "titular", "inicio"])


def resumen(m: pd.DataFrame) -> pd.DataFrame:
    filas = []
    hoy = pd.Timestamp.today().normalize()
    for g, (_, desde, hasta) in GESTIONES.items():
        d = m[m.gestion == g]
        if d.empty:
            continue
        desde, hasta = pd.Timestamp(desde), pd.Timestamp(hasta) if hasta else hoy
        anios = (hasta - desde).days / 365.25
        originales = d[d.inicio <= desde + pd.Timedelta(days=15)]
        salidas = d[d.fin.notna() & (d.fin < hasta - pd.Timedelta(days=15))]
        fin_real = d.fin.fillna(hasta)
        filas.append({
            "gestion": g, "anios": round(anios, 2), "ministros_totales": len(d),
            "salidas_anticipadas": len(salidas), "salidas_por_anio": round(len(salidas) / anios, 2),
            "permanencia_promedio_meses": round(((fin_real - d.inicio).dt.days / 30.44).mean(), 1),
            "originales": len(originales),
            "originales_hasta_el_final": int((originales.fin.isna() | (originales.fin >= hasta - pd.Timedelta(days=15))).sum()),
        })
    return pd.DataFrame(filas)


def main() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    partes = []
    for g, (titulo, _, _) in GESTIONES.items():
        ts = tablas(titulo)
        # la primera tabla con columna de ministerio es la de ministros (incluye la Jefatura de Gabinete)
        for df in ts:
            n = normalizar(df, g)
            if not n.empty and n.cartera.str.contains("Ministerio|Jefatura", case=False).any():
                partes.append(n[n.cartera.str.contains("Ministerio|Jefatura", case=False)])
                break
        time.sleep(3)
    m = pd.concat(partes, ignore_index=True)
    m.to_csv(SALIDA / "ministros.csv", index=False)
    resumen(m).to_csv(SALIDA / "resumen.csv", index=False)
    print(resumen(m).to_string())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        SALIDA.mkdir(parents=True, exist_ok=True)
        (SALIDA / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        print(traceback.format_exc())
