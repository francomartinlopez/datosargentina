"""Series que salen de planillas publicadas como archivos (INDEC, BCRA).

Cada serie del catálogo indica el lector y qué fila o columna tomar, por ejemplo:

    pobreza_personas: {fuente: archivo, lector: indec_pobreza, campo: "Pobreza/Personas"}
    pib_real:         {fuente: archivo, lector: indec_oferta_demanda, campo: "Producto Interno Bruto"}

INDEC nombra muchos archivos con el mes de publicación (cuadros_informe_pobreza_10_26.xls),
así que se prueban los últimos meses hasta encontrar uno válido. Cuando el archivo no existe,
el servidor de INDEC responde 200 con una página HTML: se descarta mirando la firma del archivo.
"""
from __future__ import annotations

import io
import re
from datetime import date
from functools import lru_cache

import pandas as pd
import requests

from . import CABECERAS, TIMEOUT

INDEC = "https://www.indec.gob.ar/ftp/cuadros/"
ARCHIVOS = {
    "pobreza": INDEC + "sociedad/cuadros_informe_pobreza_{MM}_{AA}.xls",
    "oferta_demanda": INDEC + "economia/sh_oferta_demanda_{MM}_{AA}.xls",
    "canastas": INDEC + "sociedad/serie_cba_cbt.xls",
    "supermercados": INDEC + "economia/serie_supermercados.xlsx",
    "itcrm": "https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/ITCRMSerie.xlsx",
    "ingresos": INDEC + "sociedad/cuadros_informe_ingresos_{MM}_{AA}.xls",
    "cin": INDEC + "economia/cin_{T}_{AAAA}.xls",
}
PAGINA_DEUDA = "https://www.argentina.gob.ar/economia/finanzas/datos-trimestrales-de-la-deuda"
PAGINA_PROVINCIAS = "https://www.argentina.gob.ar/economia/sechacienda/coordinacion-fiscal-provincial/ejecucion-presupuestaria-provincial/ejecuciones"
FIRMAS = (b"\xd0\xcf\x11\xe0", b"PK\x03\x04")  # xls (OLE2) y xlsx (zip)


def candidatos(patron: str, meses_atras: int = 15) -> list[str]:
    if "{T}" in patron:  # trimestre en números romanos: cin_II_2026.xls
        hoy = pd.Timestamp(date.today())
        out = []
        for k in range(8):
            f = hoy - pd.DateOffset(months=3 * k)
            out.append(patron.format(T=["I", "II", "III", "IV"][(f.month - 1) // 3], AAAA=f.year))
        return out
    if "{MM}" not in patron:
        return [patron]
    hoy = pd.Timestamp(date.today()).replace(day=1)
    return [patron.format(MM=f"{f.month:02d}", AA=f"{f.year % 100:02d}")
            for f in (hoy - pd.DateOffset(months=k) for k in range(meses_atras))]


@lru_cache(maxsize=None)
def bajar(clave: str) -> bytes:
    """Devuelve el archivo más reciente disponible para la clave (con caché por corrida)."""
    errores = []
    for url in candidatos(ARCHIVOS[clave]):
        try:
            r = requests.get(url, headers=CABECERAS, timeout=TIMEOUT)
        except requests.RequestException as e:
            errores.append(f"{url}: {e}")
            continue
        if r.status_code == 200 and r.content[:4] in FIRMAS:
            return r.content
        errores.append(f"{url}: HTTP {r.status_code}")
    raise RuntimeError(f"No se encontró el archivo {clave}: {errores[:3]}")


@lru_cache(maxsize=None)
def hojas(clave: str) -> dict[str, pd.DataFrame]:
    return pd.read_excel(io.BytesIO(bajar(clave)), sheet_name=None, header=None)


def _texto(v) -> str:
    return "" if pd.isna(v) else str(v).strip()


# ---------- Lectores ----------

def semestre_a_fecha(etiqueta: str) -> pd.Timestamp | None:
    """'1er. semestre 2017' -> 2017-01-01; '2do. semestre 2019 (1)' -> 2019-07-01."""
    m = re.search(r"(1|2)\D*semestre\D*(\d{4})", etiqueta, flags=re.I)
    if not m:
        return None
    return pd.Timestamp(int(m.group(2)), 1 if m.group(1) == "1" else 7, 1)


def indec_pobreza(campo: str, h: dict | None = None) -> pd.Series:
    """Cuadro 1 del informe de pobreza. campo: 'Pobreza/Personas', 'Indigencia/Hogares', etc."""
    df = (h or hojas("pobreza"))["Cuadro 1"]
    bloque, fila = campo.split("/")
    fila_enc = next(i for i in range(len(df)) if _texto(df.iat[i, 0]).lower() == "indicador")
    fechas = [semestre_a_fecha(_texto(v)) for v in df.iloc[fila_enc, 1:]]
    en_bloque = False
    for i in range(fila_enc + 1, len(df)):
        etiqueta = _texto(df.iat[i, 0])
        if etiqueta.lower() == bloque.lower():
            en_bloque = True
        elif en_bloque and etiqueta.lower() == fila.lower():
            valores = pd.to_numeric(df.iloc[i, 1:], errors="coerce").values
            s = pd.Series({f: v for f, v in zip(fechas, valores) if f is not None and pd.notna(v)}, dtype=float)
            return s.sort_index()
    raise ValueError(f"No se encontró {campo} en el cuadro de pobreza")


def indec_trimestral(df: pd.DataFrame, etiqueta: str, col_etiqueta: int = 1) -> pd.Series:
    """Cuadros anchos de cuentas nacionales: una fila de años y otra de trimestres."""
    fila_trim = next(i for i in range(len(df)) if any("trimestre" in _texto(v).lower() for v in df.iloc[i]))
    anios = pd.Series([_texto(v) for v in df.iloc[fila_trim - 1]]).replace("", pd.NA).ffill()
    fechas = {}
    for j, v in enumerate(df.iloc[fila_trim]):
        m = re.match(r"(\d)\D*trimestre", _texto(v).lower())
        a = re.match(r"(\d{4})", str(anios.iat[j])) if pd.notna(anios.iat[j]) else None
        if m and a:
            fechas[j] = pd.Timestamp(int(a.group(1)), 3 * (int(m.group(1)) - 1) + 1, 1)
    fila = next(i for i in range(fila_trim + 1, len(df))
                if _texto(df.iat[i, col_etiqueta]).lower().startswith(etiqueta.lower()))
    s = pd.Series({f: pd.to_numeric(df.iat[fila, j], errors="coerce") for j, f in fechas.items()}, dtype=float)
    return s.dropna().sort_index()


def indec_oferta_demanda(campo: str, h: dict | None = None) -> pd.Series:
    """Cuadro 1 (millones de pesos de 2004). campo: inicio de la fila, p. ej. 'Producto Interno Bruto'."""
    return indec_trimestral((h or hojas("oferta_demanda"))["cuadro 1"], campo)


def indec_canastas(campo: str, h: dict | None = None) -> pd.Series:
    """Serie de CBA y CBT por adulto equivalente. campo: 'CBT' o 'CBA'."""
    df = (h or hojas("canastas"))["CBA-CBT"]
    col = 3 if campo.upper() == "CBT" else 1
    fechas = pd.to_datetime(df.iloc[:, 0], errors="coerce", format="mixed")
    s = pd.Series(pd.to_numeric(df.iloc[:, col], errors="coerce").values, index=fechas)
    return s[s.index.notna()].dropna().sort_index()


def bcra_itcrm(campo: str = "ITCRM", h: dict | None = None) -> pd.Series:
    """Tipo de cambio real multilateral, promedio mensual (base 17-12-15 = 100)."""
    df = (h or hojas("itcrm"))["ITCRM y bilaterales prom. mens."]
    fila_enc = next(i for i in range(len(df)) if _texto(df.iat[i, 0]).lower() == "período")
    col = next(j for j, v in enumerate(df.iloc[fila_enc]) if _texto(v) == campo)
    fechas = pd.to_datetime(df.iloc[fila_enc + 1:, 0], errors="coerce", format="mixed")
    s = pd.Series(pd.to_numeric(df.iloc[fila_enc + 1:, col], errors="coerce").values, index=fechas)
    s = s[s.index.notna()].dropna()
    s.index = s.index.to_period("M").to_timestamp()
    return s.sort_index()


def indec_supermercados_provincias(h: dict | None = None) -> pd.DataFrame:
    """Cuadro 5: ventas totales a precios corrientes por jurisdicción (miles de pesos).
    Devuelve un DataFrame con una columna por jurisdicción e índice mensual."""
    df = (h or hojas("supermercados"))["Cuadro 5."]
    fila_jur = next(i for i in range(len(df)) if _texto(df.iat[i, 0]).lower() == "período")
    jur = pd.Series([_texto(v) for v in df.iloc[fila_jur]]).replace("", pd.NA).ffill()
    grupos = [_texto(v) for v in df.iloc[fila_jur + 1]]
    columnas = {jur.iat[j]: j for j in range(1, df.shape[1]) if grupos[j].lower() == "total" and pd.notna(jur.iat[j])}
    fechas = pd.to_datetime(df.iloc[fila_jur + 2:, 0], errors="coerce", format="mixed")
    datos = {n: pd.to_numeric(df.iloc[fila_jur + 2:, j], errors="coerce").values for n, j in columnas.items()}
    out = pd.DataFrame(datos, index=fechas)
    return out[out.index.notna()].dropna(how="all").sort_index()


def indec_supermercados_precios(h: dict | None = None) -> pd.Series:
    """Cuadro 2: índice de precios implícitos de supermercados (nacional, 2017=100)."""
    df = (h or hojas("supermercados"))["Cuadro 2"]
    fila = next(i for i in range(len(df)) if _texto(df.iat[i, 0]).lower() == "período")
    col = next(j for j, v in enumerate(df.iloc[fila]) if "precios implícitos" in _texto(v).lower())
    fechas = pd.to_datetime(df.iloc[fila + 1:, 0], errors="coerce", format="mixed")
    s = pd.Series(pd.to_numeric(df.iloc[fila + 1:, col], errors="coerce").values, index=fechas)
    s = s[s.index.notna()].dropna()
    s.index = s.index.to_period("M").to_timestamp()
    return s.sort_index()


def _cuadro_deciles(df: pd.DataFrame, columnas: dict[str, str]) -> list[dict]:
    """Lee un cuadro de deciles de la EPH buscando cada columna por su encabezado."""
    fila_enc = next(i for i in range(len(df)) if any("ingreso medio por decil" in _texto(v).lower() for v in df.iloc[i]))
    encabezados = {j: _texto(df.iat[fila_enc, j]).lower() for j in range(df.shape[1])}
    cols = {}
    for clave, texto in columnas.items():
        cols[clave] = next(j for j, e in encabezados.items() if e.startswith(texto.lower()))
    desde = next(j for j, e in encabezados.items() if e == "desde")
    hasta = next(j for j, e in encabezados.items() if e == "hasta")
    filas = []
    for i in range(fila_enc + 1, len(df)):
        d = pd.to_numeric(df.iat[i, 0], errors="coerce")
        if pd.isna(d) or not 1 <= d <= 10:
            continue
        fila = {"decil": int(d), "desde": float(df.iat[i, desde]), "hasta": float(df.iat[i, hasta])}
        for clave, j in cols.items():
            fila[clave] = float(pd.to_numeric(df.iat[i, j], errors="coerce"))
        filas.append(fila)
    return filas


def indec_distribucion_ingreso(h: dict | None = None) -> dict:
    """Último informe de distribución del ingreso (EPH): deciles de personas y de hogares."""
    h = h or hojas("ingresos")
    titulo = _texto(h["Cuadro 1"].iat[0, 0])
    m = re.search(r"(primer|segundo|tercer|cuarto) trimestre( de)? (\d{4})", titulo, flags=re.I)
    trimestre = {"primer": 1, "segundo": 2, "tercer": 3, "cuarto": 4}[m.group(1).lower()] if m else None
    personas = _cuadro_deciles(h["Cuadro 1"], {"poblacion_miles": "población por decil", "ingreso_total_millones": "ingreso total por decil",
                                              "porcentaje_ingreso": "porcentaje del ingreso", "ingreso_medio": "ingreso medio por decil"})
    hogares = _cuadro_deciles(h["Cuadro 9"], {"hogares_miles": "hogares por decil", "poblacion_miles": "población por decil",
                                             "ingreso_total_millones": "ingreso total por decil", "porcentaje_ingreso": "porcentaje del ingreso",
                                             "ingreso_medio": "ingreso medio por decil"})
    return {"anio": int(m.group(3)) if m else None, "trimestre": trimestre, "personas": personas, "hogares": hogares}


def indec_cin(campo: str, h: dict | None = None) -> pd.Series:
    """Cuentas internacionales (balanza de pagos), trimestral desde 2006, millones de US$.
    campo: 'Cuadro 1|1. Cuenta corriente' o, para una fila que se repite, 'Cuadro 1|3.1 Inversión directa>Pasivos'
    (la primera fila 'Pasivos' después de '3.1 Inversión directa')."""
    hoja, etiqueta = campo.split("|")
    df = (h or hojas("cin"))[hoja]
    fila_t = next(i for i in range(len(df)) if any(re.match(r"\d{4}T[1-4]", _texto(v)) for v in df.iloc[i]))
    fechas = {}
    for j, v in enumerate(df.iloc[fila_t]):
        m = re.match(r"(\d{4})T([1-4])", _texto(v))
        if m:
            fechas[j] = pd.Timestamp(int(m.group(1)), 3 * (int(m.group(2)) - 1) + 1, 1)
    partes = etiqueta.split(">")
    i = fila_t
    for parte in partes:
        i = next(k for k in range(i + 1, len(df)) if _texto(df.iat[k, 0]).lower().startswith(parte.strip().lower()))
    s = pd.Series({f: pd.to_numeric(df.iat[i, j], errors="coerce") for j, f in fechas.items()}, dtype=float)
    return s.dropna().sort_index()


# ---------- Deuda de la Administración Central (Secretaría de Finanzas) ----------

def _trimestre_de(dia: str) -> pd.Timestamp:
    """'30/06/2026' -> 2026-04-01 (inicio del trimestre del saldo)."""
    d, m, a = (int(x) for x in re.findall(r"\d+", dia)[:3])
    return pd.Timestamp(a, 3 * ((m - 1) // 3) + 1, 1)


@lru_cache(maxsize=None)
def deuda_archivos() -> tuple[bytes, ...]:
    """Todos los Excel trimestrales de deuda publicados (desde 2019), del más viejo al más nuevo."""
    r = requests.get(PAGINA_DEUDA, headers=CABECERAS, timeout=TIMEOUT)
    enlaces = set(re.findall(r'href="([^"]*deuda_publica_\d{2}-\d{2}-\d{4}[^"]*\.xlsx)"', r.text))
    def clave(u):
        d, m, a = re.search(r"deuda_publica_(\d{2})-(\d{2})-(\d{4})", u).groups()
        return (a, m, d)
    contenidos = []
    for u in sorted(enlaces, key=clave):
        url = u if u.startswith("http") else "https://www.argentina.gob.ar" + u
        try:
            c = requests.get(url, headers=CABECERAS, timeout=TIMEOUT).content
            if c[:4] in FIRMAS:
                contenidos.append(c)
        except requests.RequestException:
            continue
    if not contenidos:
        raise RuntimeError("No se encontraron archivos de deuda")
    return tuple(contenidos)


RUBROS_DEUDA = {
    "total": ["II- DEUDA BRUTA"],
    "titulos": ["TÍTULOS PÚBLICOS"],
    "letras": ["LETRAS DEL TESORO"],
    "organismos_internacionales": ["ORGANISMOS INTERNACIONALES"],
    "organismos_oficiales": ["ORGANISMOS OFICIALES"],
    "adelantos_bcra": ["ADELANTOS TRANSITORIOS BCRA"],
}


def _deuda_a21(contenido: bytes) -> pd.DataFrame:
    df = pd.read_excel(io.BytesIO(contenido), sheet_name="A.2.1", header=None)
    fila = next(i for i in range(len(df)) if any("saldo al" in _texto(v).lower() for v in df.iloc[i]))
    cols = {j: _trimestre_de(_texto(v)) for j, v in enumerate(df.iloc[fila]) if "saldo al" in _texto(v).lower()}
    salida = {}
    for rubro, etiquetas in RUBROS_DEUDA.items():
        filas = [i for i in range(fila + 1, len(df)) if any(_texto(df.iat[i, 1]).upper().startswith(e) for e in etiquetas)]
        if rubro == "total":
            filas = filas[:1]
        salida[rubro] = {f: sum(pd.to_numeric(df.iat[i, j], errors="coerce") or 0 for i in filas) / 1000 for j, f in cols.items()}
    return pd.DataFrame(salida)


def finanzas_deuda(campo: str) -> pd.Series:
    """Deuda bruta de la Administración Central por instrumento o acreedor, millones de US$ (saldo de fin de trimestre).
    campo: total, titulos, letras, organismos_internacionales, organismos_oficiales, adelantos_bcra, otros."""
    partes = [_deuda_a21(c) for c in deuda_archivos()]
    df = pd.concat(partes)
    df = df[~df.index.duplicated(keep="last")].sort_index()  # el archivo más nuevo manda (revisiones)
    if campo == "otros":
        return (df["total"] - df.drop(columns="total").sum(axis=1)).dropna()
    return df[campo].dropna()


def finanzas_deuda_residencia(campo: str) -> pd.Series:
    """A.4.5: deuda bruta por residencia del tenedor (externa / interna / total), millones de US$, desde 1994."""
    df = pd.read_excel(io.BytesIO(deuda_archivos()[-1]), sheet_name="A.4.5", header=None)
    fila = next(i for i in range(len(df)) if _texto(df.iat[i, 1]).lower() == "período")
    col = {"total": 2, "externa": 3, "interna": 4}[campo]
    fechas = pd.to_datetime(df.iloc[fila + 1:, 1], errors="coerce")
    s = pd.Series(pd.to_numeric(df.iloc[fila + 1:, col], errors="coerce").values, index=fechas)
    s = s[s.index.notna()].dropna() * 1000
    s.index = s.index.to_period("Q").to_timestamp()
    return s[~s.index.duplicated(keep="last")].sort_index()


# ---------- Ejecución presupuestaria provincial (serie anual AIF por provincia) ----------

RENGLONES_PROVINCIA = {
    "ingresos_totales": "VI. INGRESOS TOTALES",
    "gastos_totales": "VII. GASTOS TOTALES",
    "resultado_financiero": "VIII. RESULTADO FINANC",
    "resultado_primario": "IX. RESULTADO PRIMARIO",
    "tributarios_nacionales": "- DE ORÍGEN NACI",
    "personal": "- PERSONAL",
}


@lru_cache(maxsize=None)
def provincias_serie() -> dict[str, pd.DataFrame]:
    """{hoja (provincia o 'Consolidado'): DataFrame años x renglón} en millones de pesos corrientes."""
    r = requests.get(PAGINA_PROVINCIAS, headers=CABECERAS, timeout=TIMEOUT)
    enlaces = sorted(set(re.findall(r'href="([^"]*serie_aif-apnf-(\d{4})[^"]*\.xlsx)"', r.text)), key=lambda x: x[1])
    if not enlaces:
        raise RuntimeError("No se encontró la serie AIF provincial")
    url = enlaces[-1][0]
    url = url if url.startswith("http") else "https://www.argentina.gob.ar" + url
    contenido = requests.get(url, headers=CABECERAS, timeout=TIMEOUT).content
    return leer_provincias(pd.read_excel(io.BytesIO(contenido), sheet_name=None, header=None))


def leer_provincias(h: dict) -> dict[str, pd.DataFrame]:
    salida = {}
    for hoja, df in h.items():
        try:
            fila = next(i for i in range(len(df)) if _texto(df.iat[i, 0]).upper() == "CONCEPTO")
        except StopIteration:
            continue
        anios = {j: int(float(v)) for j, v in enumerate(df.iloc[fila]) if re.fullmatch(r"\d{4}(\.0)?", _texto(v))}
        datos = {}
        for clave, prefijo in RENGLONES_PROVINCIA.items():
            i = next((k for k in range(fila + 1, len(df)) if _texto(df.iat[k, 0]).upper().startswith(prefijo)), None)
            if i is not None:
                datos[clave] = {pd.Timestamp(a, 1, 1): pd.to_numeric(df.iat[i, j], errors="coerce") for j, a in anios.items()}
        salida[re.sub(r"\s+", " ", hoja).strip()] = pd.DataFrame(datos).sort_index()
    return salida


def hacienda_provincias(campo: str) -> pd.Series:
    """Consolidado de las 24 jurisdicciones, anual. campo: un renglón de RENGLONES_PROVINCIA."""
    return provincias_serie()["Consolidado"][campo].dropna()


LECTORES = {
    "indec_pobreza": indec_pobreza,
    "indec_oferta_demanda": indec_oferta_demanda,
    "indec_canastas": indec_canastas,
    "bcra_itcrm": bcra_itcrm,
    "indec_cin": indec_cin,
    "finanzas_deuda": finanzas_deuda,
    "finanzas_deuda_residencia": finanzas_deuda_residencia,
    "hacienda_provincias": hacienda_provincias,
}


def extraer(definicion: dict) -> pd.Series:
    return LECTORES[definicion["lector"]](definicion.get("campo"))
