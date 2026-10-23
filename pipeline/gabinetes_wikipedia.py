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
    """Lleva una tabla de ministros a: gestion, cartera, titular, inicio, fin.

    Las tablas tienen encabezados de una o dos filas; con dos se usa la de abajo
    (Nombre, Inicio, Final). Las tablas de secretarías se descartan.
    """
    df = df.copy()
    df.columns = [str(c[-1] if isinstance(c, tuple) else c) for c in df.columns]
    bajas = [c.lower() for c in df.columns]
    if any("secretar" in c for c in bajas[1:]):
        return pd.DataFrame()
    cartera = next((c for c in df.columns if c.lower().startswith(("ministerio", "cartera", "cargo"))), None)
    nombre = [c for c in df.columns if c.lower().startswith(("nombre", "titular"))]
    inicio = next((c for c in df.columns if c.lower().startswith("inicio")), None)
    fin = next((c for c in df.columns if c.lower().startswith(("final", "fin"))), None)
    if cartera is None or not nombre or inicio is None:
        return pd.DataFrame()
    titular = df[nombre].astype(str).apply(lambda r: next((v for v in r[::-1] if v not in ("nan", "")), ""), axis=1)
    limpiar = lambda x: x.astype(str).str.replace(r"\[.*?\]", "", regex=True).str.replace("\u200b", "").str.strip()
    out = pd.DataFrame({
        "gestion": gestion,
        "cartera": limpiar(df[cartera]),
        "titular": limpiar(titular),
        "inicio": df[inicio].map(fecha),
        "fin": df[fin].map(fecha) if fin else None,
    })
    return out.dropna(subset=["inicio"]).drop_duplicates(subset=["cartera", "titular", "inicio"])


def clasificar(m: pd.DataFrame) -> pd.DataFrame:
    """Motivo de salida de cada ministro:
    - hasta_el_final: terminó con la gestión (o sigue en funciones)
    - reemplazo: otra persona asumió la misma cartera (renuncia o desplazamiento)
    - traslado: la misma persona pasó a otra cartera
    - reestructuracion: la cartera se eliminó, fusionó o cambió de nombre
    """
    m = m.copy()
    hoy = pd.Timestamp.today().normalize()
    motivos = []
    for _, r in m.iterrows():
        _, desde, hasta = GESTIONES[r.gestion]
        hasta = pd.Timestamp(hasta) if hasta else hoy
        if pd.isna(r.fin) or r.fin >= hasta - pd.Timedelta(days=15):
            motivos.append("hasta_el_final")
            continue
        misma = m[(m.gestion == r.gestion) & (m.cartera == r.cartera) & (m.titular != r.titular)
                  & (m.inicio >= r.fin - pd.Timedelta(days=5)) & (m.inicio <= r.fin + pd.Timedelta(days=90))]
        otra = m[(m.gestion == r.gestion) & (m.titular == r.titular) & (m.cartera != r.cartera)
                 & (m.inicio >= r.fin - pd.Timedelta(days=5)) & (m.inicio <= r.fin + pd.Timedelta(days=30))]
        motivos.append("reemplazo" if len(misma) else "traslado" if len(otra) else "reestructuracion")
    m["motivo_salida"] = motivos
    return m


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
        fin_real = d.fin.fillna(hasta)
        n = d.motivo_salida.value_counts()
        filas.append({
            "gestion": g, "anios": round(anios, 2), "ministros": len(d),
            "reemplazos": int(n.get("reemplazo", 0)), "reemplazos_por_anio": round(n.get("reemplazo", 0) / anios, 2),
            "traslados": int(n.get("traslado", 0)), "reestructuraciones": int(n.get("reestructuracion", 0)),
            "permanencia_promedio_meses": round(((fin_real - d.inicio).dt.days / 30.44).mean(), 1),
            "originales": len(originales),
            "originales_hasta_el_final": int((originales.motivo_salida == "hasta_el_final").sum()),
        })
    return pd.DataFrame(filas)


def main() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    partes = []
    for g, (titulo, _, _) in GESTIONES.items():
        ts = tablas(titulo)
        crudo = SALIDA / "crudo"
        crudo.mkdir(parents=True, exist_ok=True)
        for i, df in enumerate(ts):
            df.to_csv(crudo / f"{g.replace(' ', '_')}__{i}.csv", index=False)
        # la primera tabla con columna de ministerio es la de ministros (incluye la Jefatura de Gabinete)
        for df in ts:
            n = normalizar(df, g)
            if not n.empty and n.cartera.str.contains("Ministerio|Jefatura", case=False).any():
                partes.append(n[n.cartera.str.contains("Ministerio|Jefatura", case=False)])
                break
        time.sleep(3)
    m = clasificar(pd.concat(partes, ignore_index=True))
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
