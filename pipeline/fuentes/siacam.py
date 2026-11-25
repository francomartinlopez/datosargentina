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
    if campo.startswith("mineral:"):
        s = serie_mineral(campo.split(":", 1)[1])
        return s[s.index >= pd.Timestamp(2023, 1, 1)]
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


# ---------- Exportaciones por mineral: informe mensual «Exportaciones mineras de Argentina» ----------

URL_MINERAL = "https://www.argentina.gob.ar/sites/default/files/{a}.{m:02d}_exportaciones_mineras_{prep}_argentina.pdf"
CACHE_MINERAL = Path(__file__).resolve().parents[2] / "data" / "derivados" / "siacam_minerales.csv"
DESDE_MINERAL = (2023, 1)
_U = r"(?:USD|US\$) ?([\d\.,]+) millones"
# (clave, patrón del dato del mes, patrón del acumulado del año)
PRODUCTOS = [
    ("oro", r"participaci[oó]n del oro con " + _U, r"el oro aport[oó] " + _U),
    ("plata", r"la plata con " + _U, r"la plata " + _U + r" \(\d"),
    ("otros_metaliferos", r"restantes " + _U.replace(" millones", r" millones(?: metal[ií]feros)?"), r"resto de los minerales metal[ií]feros " + _U),
    ("litio", r"se exportaron un total de " + _U, r"ventas de litio al exterior alcanzaron (?:los )?" + _U),
    ("resto", r"resto de los productos mineros alcanzaron (?:los )?" + _U, r"resto de las exportaciones alcanzaron (?:los )?" + _U),
]


def leer_informe_mineral(t: str) -> dict | None:
    m = re.search(r"exportaciones de minerales del mes de (\w+) de (\d{4}),? totalizaron", t)
    if not m or m.group(1).lower() not in MESES:
        return None
    fila = {"fecha": f"{m.group(2)}-{MESES[m.group(1).lower()]:02d}-01"}
    n = re.search(r"(?:primeros (\w+) meses|(\d+) meses) (?:de|del) (?:\d{4}|año)", t[t.find("minerales metal"):])
    if n:
        k = n.group(1) or n.group(2)
        k = int(k) if k.isdigit() else NUMEROS.get(k.lower())
        if k:
            fila["acumulado_meses"] = k
    for clave, mes, acum in PRODUCTOS:
        a = re.search(mes, t)
        if a:
            fila[clave] = numero(a.group(1))
        b = re.search(acum, t)
        if b and "acumulado_meses" in fila:
            fila[clave + "_acumulado"] = numero(b.group(1))
    # mismo mes del año anterior: oro y plata traen la diferencia en millones; el litio, la variación en %
    for clave, nombre in (("oro", "oro"), ("plata", "plata")):
        d = re.search(r"exportaciones de " + nombre + r"[^.(]{0,120}?\(([\d\.,]+) millones (más|menos) que en \d{4}\)", t)
        if d and clave in fila:
            dif = numero(d.group(1))
            fila[clave + "_anio_anterior"] = fila[clave] - dif if d.group(2) == "más" else fila[clave] + dif
    li = re.search(r"(crecimiento|aumento|incremento|ca[ií]da|disminuci[oó]n) interanual en los montos exportados de ([\d,]+)%", t)
    if li and "litio" in fila:
        v = numero(li.group(2)) / 100
        fila["litio_anio_anterior"] = round(fila["litio"] / (1 + v if li.group(1)[0] in "cai" and not li.group(1).startswith("ca") else 1 - v), 1)
    return fila if any(c in fila for c, _, _ in PRODUCTOS) else None


@lru_cache(maxsize=None)
def tabla_mineral() -> pd.DataFrame:
    previo = pd.read_csv(CACHE_MINERAL, dtype={"informe": str}) if CACHE_MINERAL.exists() else pd.DataFrame(columns=["informe"])
    hechos = set(previo["informe"])
    hoy = pd.Timestamp.today()
    nuevos, (a, m) = [], DESDE_MINERAL
    while (a, m) <= (hoy.year, hoy.month):
        clave = f"{a}.{m:02d}"
        if clave not in hechos:
            for prep in ("en", "de"):
                try:
                    r = requests.get(URL_MINERAL.format(a=a, m=m, prep=prep), headers=CABECERAS, timeout=TIMEOUT)
                except requests.RequestException:
                    continue
                if r.status_code == 200 and r.content[:4] == b"%PDF":
                    try:
                        fila = leer_informe_mineral(texto_pdf(r.content))
                    except Exception:
                        fila = None
                    if fila:
                        nuevos.append({"informe": clave, **fila})
                    break
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    if not nuevos:
        return previo
    out = pd.concat([previo, pd.DataFrame(nuevos)], ignore_index=True).sort_values("informe")
    CACHE_MINERAL.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(CACHE_MINERAL, index=False)
    return out


def serie_mineral(producto: str, t: pd.DataFrame | None = None) -> pd.Series:
    """Millones de US$ por mes de un producto (oro, plata, otros_metaliferos, litio, resto): diferencia
    entre acumulados del año consecutivos y, si falta, el dato del mes del propio informe."""
    t = tabla_mineral() if t is None else t
    if t.empty or producto not in t.columns:
        raise ValueError(f"SIACAM: no hay datos de {producto}")
    propio, acum = {}, {}
    for _, r in t.iterrows():
        f = pd.Timestamp(r["fecha"])
        if pd.notna(r.get(producto)):
            propio[f] = r[producto]
        col = producto + "_acumulado"
        if col in r and pd.notna(r.get(col)) and pd.notna(r.get("acumulado_meses")):
            acum[(f.year, int(r["acumulado_meses"]))] = r[col]
    s = {}
    for (anio, n), v in acum.items():
        if n > 1 and (anio, n - 1) in acum:
            s[pd.Timestamp(anio, n, 1)] = v - acum[(anio, n - 1)]
    for f, v in propio.items():
        s.setdefault(f, v)
    if producto + "_anio_anterior" in t.columns:
        for _, r in t.iterrows():
            if pd.notna(r.get(producto + "_anio_anterior")):
                s.setdefault(pd.Timestamp(r["fecha"]) - pd.DateOffset(years=1), r[producto + "_anio_anterior"])
    # un mes sin informe propio: acumulado del mes siguiente − acumulado del anterior − dato del mes siguiente
    for (anio, n), v in acum.items():
        f = pd.Timestamp(anio, n - 1, 1) if n > 1 else None
        siguiente = pd.Timestamp(anio, n, 1)
        if f is None or f in s or siguiente not in propio:
            continue
        previo = 0 if n == 2 else acum.get((anio, n - 2))
        if previo is not None:
            s[f] = v - previo - propio[siguiente]
    return pd.Series(s, dtype=float).sort_index()
