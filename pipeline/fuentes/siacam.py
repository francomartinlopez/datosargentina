"""Exportaciones mineras: informe mensual «Origen provincial de las exportaciones mineras» de la
Secretaría de Minería (Dirección Nacional de Promoción y Economía Minera, con datos de Aduana).

Cada informe (PDF en argentina.gob.ar) trae, para el mes anterior:
- el total exportado por la minería y su variación interanual (de ahí sale también el mismo mes del
  año anterior), y el acumulado del año;
- lo exportado por Santa Cruz, San Juan y las provincias del NOA (Catamarca, Jujuy y Salta), con la
  parte que fue oro, plata o litio.

Se bajan todos los informes publicados (desde octubre de 2022) y los resultados se guardan en
data/derivados/siacam_exportaciones.csv; en cada corrida solo se leen los informes nuevos.
Los meses sin informe propio se completan con la diferencia de dos acumulados del año.
"""
from __future__ import annotations

import io
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd
import requests

from . import CABECERAS, TIMEOUT

URL = "https://www.argentina.gob.ar/sites/default/files/{a}.{m:02d}_origen_provincial_de_las_exportaciones_mineras.pdf"
CACHE = Path(__file__).resolve().parents[2] / "data" / "derivados" / "siacam_exportaciones.csv"
DESDE = (2022, 10)
MESES = {m: i + 1 for i, m in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                                          "septiembre", "octubre", "noviembre", "diciembre"])}
NUMEROS = {"un": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
           "diez": 10, "once": 11, "doce": 12}
SUBE = ("incremento", "aumento", "crecimiento", "suba")


def numero(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def texto_pdf(contenido: bytes) -> str:
    from pypdf import PdfReader
    t = " ".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(contenido)).pages)
    return re.sub(r"\s+", " ", t)


def _seccion(t: str, titulo: str, siguiente: str | None) -> str:
    i = t.find(titulo)
    if i < 0:
        return ""
    j = t.find(siguiente, i + len(titulo)) if siguiente else -1
    return t[i: j if j > 0 else i + 6000]


def _pct(s: str, patron: str) -> float | None:
    m = re.search(patron, s)
    return numero(m.group(1)) if m else None


def leer_informe(t: str) -> dict | None:
    """Datos del mes que informa el texto de un informe. None si no se reconoce el formato."""
    m = re.search(r"(?:Durante el|En el) mes de (\w+) de (\d{4}),? el sector minero realiz[oó] exportaciones por "
                  r"(?:USD|US\$) ?([\d\.,]+) millones?,? lo que implic[aó] (?:una|un) (\w+) interanual del ([\d,]+)", t)
    if not m:
        return None
    mes, anio, valor, sentido, var = m.groups()
    if mes.lower() not in MESES:
        return None
    valor, var = numero(valor), numero(var)
    fila = {"fecha": f"{anio}-{MESES[mes.lower()]:02d}-01", "total": valor,
            "total_anio_anterior": round(valor / (1 + (var if sentido.lower().startswith(SUBE) else -var) / 100), 1)}
    a = re.search(r"primeros (\w+) meses de (\d{4}),? las exportaciones mineras totalizaron (?:USD|US\$) ?([\d\.,]+) millones", t)
    if a:
        n = a.group(1)
        n = int(n) if n.isdigit() else NUMEROS.get(n.lower())
        if n:
            fila["acumulado_meses"], fila["acumulado"] = n, numero(a.group(3))
    # provincias: Santa Cruz, San Juan y NOA, cada una con su valor del mes y la parte de cada producto
    alcanzaron = r"exportaciones mineras(?: de octubre de \d{4}| de \w+ de \d{4})? alcanzaron (?:los )?(?:USD|US\$) ?([\d\.,]+) millones"
    sc = _seccion(t, "Exportaciones mineras de Santa Cruz", "Exportaciones mineras de San Juan")
    sj = _seccion(t, "Exportaciones mineras de San Juan", "Exportaciones mineras de provincias del NOA")
    noa = _seccion(t, "Exportaciones mineras de provincias del NOA", "Principales proyectos")
    for clave, s in (("santa_cruz", sc), ("san_juan", sj)):
        v = re.search(alcanzaron, s)
        if v:
            fila[clave] = numero(v.group(1))
    # el NOA se busca por su frase (el orden del texto del PDF cambia según el año)
    v = re.search(r"En las provincias del NOA \(Catamarca, Jujuy y Salta\),? las exportaciones mineras[^.]{0,40}? alcanzaron (?:los )?(?:USD|US\$) ?([\d\.,]+) millones", t)
    if v:
        fila["noa"] = numero(v.group(1))
        noa = t
    # el mismo mes del año anterior, que cada sección cita entre paréntesis
    previos = (("santa_cruz", sc, r"\(cuando export[oó] (?:USD|US\$) ?([\d\.,]+) millones en minerales\)"),
               ("san_juan", sj, r"\(cuando la miner[ií]a sanjuanina export[oó] (?:USD|US\$) ?([\d\.,]+) millones\)"),
               ("noa", t, r"\(mes en (?:el que|donde) las provincias mencionadas exportaron minerales por (?:USD|US\$) ?([\d\.,]+) millones\)"))
    for clave, s, patron in previos:
        v = re.search(patron, s)
        if v:
            fila[clave + "_anio_anterior"] = numero(v.group(1))
    if "santa_cruz" in fila:
        fila["santa_cruz_oro_pct"] = _pct(sc, r"el oro represent[oó] el ([\d,]+)%")
        fila["santa_cruz_plata_pct"] = _pct(sc, r"la plata (?:el|represent[oó] el) ([\d,]+)%")
    if "san_juan" in fila:
        fila["san_juan_oro_pct"] = _pct(sj, r"(?:este mineral|el oro) represent[oó] el ([\d,]+)%")
    if "noa" in fila:
        fila["noa_litio_pct"] = _pct(noa, r"[Ee]l litio (?:explic[oó]|represent[oó]) el ([\d,]+)%")
    return fila


def _bajar(a: int, m: int) -> bytes | None:
    try:
        r = requests.get(URL.format(a=a, m=m), headers=CABECERAS, timeout=TIMEOUT)
    except requests.RequestException:
        return None
    return r.content if r.status_code == 200 and r.content[:4] == b"%PDF" else None


@lru_cache(maxsize=None)
def tabla() -> pd.DataFrame:
    previo = pd.read_csv(CACHE, dtype={"informe": str}) if CACHE.exists() else pd.DataFrame(columns=["informe"])
    hechos = set(previo["informe"])
    hoy = pd.Timestamp.today()
    nuevos, (a, m) = [], DESDE
    while (a, m) <= (hoy.year, hoy.month):
        clave = f"{a}.{m:02d}"
        if clave not in hechos:
            c = _bajar(a, m)
            if c:
                try:
                    fila = leer_informe(texto_pdf(c))
                except Exception:
                    fila = None
                if fila:
                    nuevos.append({"informe": clave, **fila})
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    if not nuevos:
        return previo
    out = pd.concat([previo, pd.DataFrame(nuevos)], ignore_index=True).sort_values("informe")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(CACHE, index=False)
    return out


def total_mensual(t: pd.DataFrame) -> pd.Series:
    """Total mensual. Primero, la diferencia entre dos acumulados del año consecutivos: así la suma del
    año coincide con el acumulado oficial, que incorpora las revisiones de los meses anteriores (por eso
    un mes puede diferir del valor que dio su propio informe). Si falta, el dato del propio informe; si
    tampoco está, el mismo mes informado un año después (vía la variación interanual)."""
    propio, anterior, acum = {}, {}, {}
    for _, r in t.iterrows():
        f = pd.Timestamp(r["fecha"])
        propio[f] = r["total"]
        if pd.notna(r.get("total_anio_anterior")):
            anterior[f - pd.DateOffset(years=1)] = r["total_anio_anterior"]
        if pd.notna(r.get("acumulado")):
            acum[(f.year, int(r["acumulado_meses"]))] = r["acumulado"]
    s = {}
    for (anio, n), v in acum.items():
        if n > 1 and (anio, n - 1) in acum:
            s[pd.Timestamp(anio, n, 1)] = v - acum[(anio, n - 1)]
    for f, v in propio.items():
        s.setdefault(f, v)
    for f, v in anterior.items():
        s.setdefault(f, v)
    serie = pd.Series(s, dtype=float).sort_index()
    return serie[serie.index >= pd.Timestamp(2022, 1, 1)]


def serie(campo: str) -> pd.Series:
    """campo: total, santa_cruz, san_juan, noa, oro (Santa Cruz + San Juan), plata (Santa Cruz) o litio (NOA).
    Millones de US$ FOB por mes."""
    t = tabla()
    if t.empty:
        raise ValueError("SIACAM: no se pudo leer ningún informe")
    if campo == "total":
        return total_mensual(t)
    t = t.assign(fecha=pd.to_datetime(t["fecha"])).set_index("fecha").sort_index()
    col = lambda c: pd.to_numeric(t.get(c), errors="coerce") if c in t else pd.Series(index=t.index, dtype=float)
    if campo in ("santa_cruz", "san_juan", "noa"):
        s = col(campo)
        anterior = col(campo + "_anio_anterior").dropna()
        anterior.index = anterior.index - pd.DateOffset(years=1)
        s = s.combine_first(anterior)
        s = s[s.index >= pd.Timestamp(2022, 1, 1)]
    elif campo == "oro":
        s = col("santa_cruz") * col("santa_cruz_oro_pct") / 100 + col("san_juan") * col("san_juan_oro_pct") / 100
    elif campo == "plata":
        s = col("santa_cruz") * col("santa_cruz_plata_pct") / 100
    elif campo == "litio":
        s = col("noa") * col("noa_litio_pct") / 100
    else:
        raise ValueError(f"SIACAM: campo desconocido {campo}")
    return s.dropna()
