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
from pathlib import Path

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
    "ib_anexo": "https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/informes/informe-bancos-anexo.xlsx",
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
    "tributarios_provinciales": "- DE ORÍGEN PROV",
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
            sin_tilde = lambda s: s.upper().replace("Í", "I").replace("Ó", "O").replace("  ", " ")
            i = next((k for k in range(fila + 1, len(df)) if sin_tilde(_texto(df.iat[k, 0])).startswith(sin_tilde(prefijo))), None)
            if i is not None:
                datos[clave] = {pd.Timestamp(a, 1, 1): pd.to_numeric(df.iat[i, j], errors="coerce") for j, a in anios.items()}
        salida[re.sub(r"\s+", " ", hoja).strip()] = pd.DataFrame(datos).sort_index()
    return salida


def hacienda_provincias(campo: str) -> pd.Series:
    """Consolidado de las 24 jurisdicciones, anual. campo: un renglón de RENGLONES_PROVINCIA."""
    return provincias_serie()["Consolidado"][campo].dropna()


# ---------- BCRA: proveedores no financieros de crédito (fintech, billeteras, tarjetas no bancarias) ----------

PNFC = "https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/informes/anexo-estadistico-proveedores-no-financieros-credito-{mes}-{anio}.xlsx"
MESES_ES = ["diciembre", "noviembre", "octubre", "septiembre", "agosto", "julio", "junio", "mayo", "abril", "marzo", "febrero", "enero"]


@lru_cache(maxsize=None)
def pnfc_hojas() -> dict[str, pd.DataFrame]:
    """Anexo estadístico del informe semestral más reciente (se prueban los meses hacia atrás)."""
    hoy = date.today()
    for anio in (hoy.year, hoy.year - 1, hoy.year - 2):
        for mes in MESES_ES:
            if anio == hoy.year and MESES_ES.index(mes) < 11 - (hoy.month - 1):
                continue  # meses todavía no llegados
            try:
                r = requests.get(PNFC.format(mes=mes, anio=anio), headers=CABECERAS, timeout=TIMEOUT)
            except requests.RequestException:
                continue
            if r.status_code == 200 and r.content[:4] in FIRMAS:
                return pd.read_excel(io.BytesIO(r.content), sheet_name=None, header=None)
    raise RuntimeError("No se encontró el anexo del informe de proveedores no financieros de crédito")


def leer_pnfc(h: dict, campo: str) -> pd.Series:
    """campo = "hoja|fila", tomada del bloque "Ratio de irregularidad" (en %)."""
    hoja, fila = campo.split("|")
    df = next(v for k, v in h.items() if k.strip().lower().startswith(hoja.strip().lower()))
    inicio = next(i for i in range(len(df)) if _texto(df.iat[i, 0]).lower().startswith("ratio de irregularidad"))
    fechas = df.iloc[inicio + 1]
    for i in range(inicio + 2, len(df)):
        if _texto(df.iat[i, 0]).lower() == fila.strip().lower():
            vals = pd.to_numeric(df.iloc[i, 1:], errors="coerce").values
            idx = pd.to_datetime(fechas.iloc[1:], errors="coerce")
            s = pd.Series(vals, index=idx, dtype=float).dropna()
            s = s[s.index.notna()] * 100
            s.index = s.index.to_period("M").to_timestamp()
            return s.sort_index()
    raise ValueError(f"PNFC: no se encontró la fila {fila} en {hoja}")


def bcra_pnfc(campo: str, h: dict | None = None) -> pd.Series:
    return leer_pnfc(h if h is not None else pnfc_hojas(), campo)


# ---------- BCRA: anexo del Informe sobre Bancos (calidad de cartera por línea, familias y empresas) ----------

def leer_ib_lineas(h: dict, campo: str) -> pd.Series:
    """campo = "bloque|fila" de la hoja "Calidad de Cartera (por líneas)", sección "Ratio de irregularidad" (en %).
    bloque es el título sin numeración, p. ej. "Familias - Total"; fila, p. ej. "Cartera irregular total"."""
    bloque, fila = (x.strip().lower() for x in campo.split("|"))
    df = next(v for k, v in h.items() if k.strip().lower().startswith("calidad de cartera (por l"))
    titulo = lambda i: re.sub(r"^[\d.]+\s*", "", _texto(df.iat[i, 0])).lower()
    inicio = next(i for i in range(len(df)) if titulo(i) == bloque)
    ratio = next(i for i in range(inicio, len(df)) if "ratio de irregularidad" in _texto(df.iat[i, 0]).lower())
    fechas = pd.to_datetime(df.iloc[ratio + 1, 1:], errors="coerce")
    for i in range(ratio + 2, len(df)):
        t = _texto(df.iat[i, 0]).lower()
        if t.startswith("fuente") or not t:
            break
        if t == fila:
            s = pd.Series(pd.to_numeric(df.iloc[i, 1:], errors="coerce").values, index=fechas, dtype=float).dropna()
            s = s[s.index.notna()]
            s.index = s.index.to_period("M").to_timestamp()
            return s.sort_index()
    raise ValueError(f"Informe sobre Bancos: no se encontró {campo}")


def bcra_ib_lineas(campo: str, h: dict | None = None) -> pd.Series:
    return leer_ib_lineas(h if h is not None else hojas("ib_anexo"), campo)


# ---------- INDEC: microdatos de la EPH (ingreso de la ocupación principal por categoría) ----------

EPH = "https://www.indec.gob.ar/ftp/cuadros/menusuperior/eph/"
EPH_CACHE = Path(__file__).resolve().parents[2] / "data" / "derivados" / "eph_ingresos.csv"
EPH_DESDE = (2016, 2)  # desde el 2do trimestre de 2016 hay ponderador de ingresos con imputación (PONDIIO)
EPH_COLUMNAS = ["cuenta_propia", "asalariado_registrado", "asalariado_no_registrado"]


def _eph_zip(anio: int, trim: int) -> bytes | None:
    suf = {1: "er", 2: "do", 3: "er", 4: "to"}[trim]
    for nombre in (f"EPH_usu_{trim}_Trim_{anio}_txt.zip", f"EPH_usu_{trim}{suf}_Trim_{anio}_txt.zip",
                   f"EPH_usu_{trim}{suf}_Trim_{anio}.zip", f"EPH_usu_{trim}_Trim_{anio}.zip",
                   f"EPH_usu_{trim}{suf}Trim_{anio}_txt.zip", f"EPH_usu_{trim}_trim_{anio}_txt.zip", f"EPH_usu_{trim}{suf}_trim_{anio}_txt.zip",
                   f"EPH_usu_{trim}{suf}Trim{anio}_txt.zip", f"EPH_usu_{trim}Trim_{anio}_txt.zip"):
        try:
            r = requests.get(EPH + nombre, headers=CABECERAS, timeout=TIMEOUT)
        except requests.RequestException:
            continue
        if r.status_code == 200 and r.content[:4] == b"PK\x03\x04":
            return r.content
    return None


def eph_promedios(contenido: bytes) -> dict:
    """Ingreso medio de la ocupación principal (P21, ponderado por PONDIIO) de los ocupados con
    ingreso: trabajadores por cuenta propia y asalariados con y sin descuento jubilatorio."""
    import numpy as np
    import zipfile
    z = zipfile.ZipFile(io.BytesIO(contenido))
    nombres = [n for n in z.namelist() if ("individual" in n.lower() or "personas" in n.lower()) and n.lower().endswith(".txt")]
    if not nombres:
        raise ValueError(f"sin archivo de personas en {z.namelist()[:6]}")
    nombre = nombres[0]
    df = pd.read_csv(z.open(nombre), sep=";", decimal=",", low_memory=False,
                     usecols=lambda c: c in {"ESTADO", "CAT_OCUP", "CAT_INAC", "P21", "PONDIIO", "PP07H", "PONDERA"})
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    o = df[(df["ESTADO"] == 1) & (df["P21"] > 0) & (df["PONDIIO"] > 0)]
    grupos = {"cuenta_propia": o[o["CAT_OCUP"] == 2], "asalariado_registrado": o[(o["CAT_OCUP"] == 3) & (o["PP07H"] == 1)],
              "asalariado_no_registrado": o[(o["CAT_OCUP"] == 3) & (o["PP07H"] == 2)]}
    out = {}
    for k, g in grupos.items():
        out[k] = float(np.average(g["P21"], weights=g["PONDIIO"])) if len(g) else None
        out["casos_" + k] = int(len(g))
    # cantidad de personas por condición de actividad (expandidas con PONDERA)
    w = df["PONDERA"]
    est, cat, aporta = df["ESTADO"], df["CAT_OCUP"], df["PP07H"]
    ina = df["CAT_INAC"] if "CAT_INAC" in df.columns else None  # desde 2026 INDEC no publica el motivo de inactividad
    ocup = est == 1
    conteos = {
        "pob_total": w.sum(),
        "pob_ocupados_asal_registrados": w[ocup & (cat == 3) & (aporta == 1)].sum(),
        "pob_ocupados_asal_no_registrados": w[ocup & (cat == 3) & (aporta != 1)].sum(),
        "pob_ocupados_cuenta_propia": w[ocup & (cat == 2)].sum(),
        "pob_ocupados_patrones": w[ocup & (cat == 1)].sum(),
        "pob_ocupados_familiares": w[ocup & ~cat.isin([1, 2, 3])].sum(),
        "pob_desocupados": w[est == 2].sum(),
        "pob_menores_10": w[est == 4].sum(),
        "pob_inactivos_total": w[est == 3].sum(),
        "pob_sin_dato": w[~est.isin([1, 2, 3, 4])].sum(),
    }
    motivos = {"jubilados": [1], "rentistas": [2], "estudiantes": [3], "amas_casa": [4], "discapacidad": [6]}
    for k, codigos in motivos.items():
        conteos["pob_inactivos_" + k] = w[(est == 3) & ina.isin(codigos)].sum() if ina is not None else None
    conteos["pob_inactivos_otros"] = w[(est == 3) & ~ina.isin([1, 2, 3, 4, 6])].sum() if ina is not None else None
    out.update({k: (int(v) if v is not None else None) for k, v in conteos.items()})
    return out


@lru_cache(maxsize=None)
def eph_tabla() -> pd.DataFrame:
    """Promedios por trimestre, guardados en data/derivados para no volver a bajar los microdatos.
    En cada corrida se calculan solo los trimestres que faltan."""
    previo = pd.read_csv(EPH_CACHE, dtype={"trimestre": str}) if EPH_CACHE.exists() else pd.DataFrame(columns=["trimestre"])
    if "pob_inactivos_total" not in previo.columns:  # caché de una versión anterior: se recalcula
        previo = pd.DataFrame(columns=["trimestre"])
    hechos = set(previo["trimestre"])
    hoy = date.today()
    nuevos, errores = [], []
    anio, trim = EPH_DESDE
    while (anio, trim) <= (hoy.year, (hoy.month - 1) // 3 + 1):
        clave = f"{anio}-T{trim}"
        if clave not in hechos:
            contenido = _eph_zip(anio, trim)
            if contenido is not None:
                try:
                    nuevos.append({"trimestre": clave, **eph_promedios(contenido)})
                except Exception as e:  # un trimestre con formato distinto no frena el resto
                    errores.append(f"{clave}: {type(e).__name__} {e}")
            else:
                errores.append(f"{clave}: no se encontró el archivo")
        trim += 1
        if trim == 5:
            anio, trim = anio + 1, 1
    EPH_CACHE.parent.mkdir(parents=True, exist_ok=True)
    (EPH_CACHE.parent / "eph_errores.txt").write_text("\n".join(errores), encoding="utf-8")
    tabla = pd.concat([previo, pd.DataFrame(nuevos)], ignore_index=True) if nuevos else previo
    if nuevos:
        EPH_CACHE.parent.mkdir(parents=True, exist_ok=True)
        tabla.sort_values("trimestre").to_csv(EPH_CACHE, index=False)
    return tabla


def indec_eph_ingresos(campo: str) -> pd.Series:
    """Serie trimestral de ingreso medio; cada trimestre se ubica en su mes central (feb, may, ago, nov),
    para deflactarlo con el IPC de mitad del trimestre."""
    t = eph_tabla()
    if campo not in t.columns or t.empty:
        raise ValueError(f"EPH: no hay datos de {campo}")
    fechas = [pd.Timestamp(int(x[:4]), 3 * int(x[-1]) - 1, 1) for x in t["trimestre"]]
    return pd.Series(pd.to_numeric(t[campo], errors="coerce").values, index=fechas, dtype=float).dropna().sort_index()


# ---------- Grupo Construya: Índice Construya (tabla mensual publicada en su web) ----------

CONSTRUYA = "https://www.grupoconstruya.com.ar/servicios/indice_construya"
MESES_ES_NUM = {m.lower(): i + 1 for i, m in enumerate(["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
                                                         "Septiembre", "Octubre", "Noviembre", "Diciembre"])}


def leer_construya(texto_html: str, campo: str = "original") -> pd.Series:
    import html as html_mod
    txt = re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", " ", texto_html)))
    filas = re.findall(r"Mes: (\w+) (\d{4}) Con Estacionalidad: ([\d.,]+).*?Desestacionalizado: ([\d.,]+)", txt)
    num = lambda v: float(v.replace(".", "").replace(",", "."))
    out = {}
    for mes, anio, orig, desest in filas:
        m = MESES_ES_NUM.get(mes.lower().replace("setiembre", "septiembre"))
        if m:
            out[pd.Timestamp(int(anio), m, 1)] = num(desest if campo == "desestacionalizado" else orig)
    if not out:
        raise ValueError("Construya: no se encontró la tabla del índice")
    return pd.Series(out, dtype=float).sort_index()


@lru_cache(maxsize=None)
def _construya_html() -> str:
    r = requests.get(CONSTRUYA, headers=CABECERAS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.content.decode("utf-8", "replace")


def construya_indice(campo: str = "original") -> pd.Series:
    return leer_construya(_construya_html(), campo or "original")


# ---------- Colegio de Escribanos de la Ciudad de Buenos Aires ----------

ESCRIBANOS = "https://www.colegio-escribanos.org.ar/noticias/{mes}-{anio}-Comparativo-anual-por-mes.xls"
MESES_NOMBRE = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def leer_escribanos(contenido: bytes, mes: int, campo: str | None = None) -> pd.Series:
    """Cada planilla mensual trae ese mismo mes de todos los años desde 2016: 'Año AAAA' | actos
    y, más a la derecha, 'Año AAAA' | monto en pesos (campo="monto")."""
    out = {}
    # la hoja con datos no siempre es la primera (algunos meses traen hojas vacías adelante)
    for df in pd.read_excel(io.BytesIO(contenido), header=None, sheet_name=None).values():
        for i in range(len(df)):
            # la columna del año no siempre es la primera: se toma la primera celda "Año AAAA" de la fila
            # (o la segunda, para el monto)
            vistos = 0
            for j in range(df.shape[1] - 1):
                m = re.match(r"Año\s+(\d{4})", _texto(df.iat[i, j]))
                if m and campo == "monto" and vistos == 0:
                    vistos = 1
                    continue
                if m:
                    v = pd.to_numeric(df.iat[i, j + 1], errors="coerce")
                    if pd.notna(v):
                        out[pd.Timestamp(int(m.group(1)), mes, 1)] = float(v)
                    break
        if out:
            break
    return pd.Series(out, dtype=float)


@lru_cache(maxsize=None)
def _escribanos_planillas() -> tuple:
    hoy = pd.Timestamp(date.today()).replace(day=1)
    out = []
    for k in range(1, 15):
        f = hoy - pd.DateOffset(months=k)
        nombres = [MESES_NOMBRE[f.month - 1]] + (["Setiembre"] if f.month == 9 else [])
        for nombre in nombres:
            try:
                r = requests.get(ESCRIBANOS.format(mes=nombre, anio=f.year), headers=CABECERAS, timeout=TIMEOUT)
            except requests.RequestException:
                continue
            if r.status_code == 200 and r.content[:4] in FIRMAS:
                out.append((r.content, f.month))
                break
    return tuple(out)


def escribanos_compraventas(campo: str | None = None) -> pd.Series:
    """Escrituras de compraventa en CABA: se juntan las planillas de los últimos 14 meses
    (cada una aporta su mes en todos los años), lo que arma la serie mensual completa.
    campo: None = cantidad de actos; "monto" = monto total escriturado en pesos."""
    partes = [leer_escribanos(c, mes, campo) for c, mes in _escribanos_planillas()]
    if not partes:
        raise RuntimeError("No se encontraron planillas del Colegio de Escribanos")
    s = pd.concat(partes)
    return s[~s.index.duplicated(keep="first")].sort_index()


def _escribanos_viejo(campo: str | None = None) -> pd.Series:
    hoy = pd.Timestamp(date.today()).replace(day=1)
    partes = []
    for k in range(1, 15):
        f = hoy - pd.DateOffset(months=k)
        nombres = [MESES_NOMBRE[f.month - 1]] + (["Setiembre"] if f.month == 9 else [])
        for nombre in nombres:
            try:
                r = requests.get(ESCRIBANOS.format(mes=nombre, anio=f.year), headers=CABECERAS, timeout=TIMEOUT)
            except requests.RequestException:
                continue
            if r.status_code == 200 and r.content[:4] in FIRMAS:
                partes.append(leer_escribanos(r.content, f.month))
                break
    if not partes:
        raise RuntimeError("No se encontraron planillas del Colegio de Escribanos")
    s = pd.concat(partes)
    s = s[~s.index.duplicated(keep="first")].sort_index()
    return s


# ---------- OEDE (Secretaría de Trabajo): aperturas y cierres de empresas ----------

PAGINA_OEDE = "https://www.argentina.gob.ar/trabajo/estadisticas/oede-estadisticas-nacionales"
COLUMNAS_OEDE = {"aperturas": 1, "cierres": 6, "neto": 8, "empresas": 9}


@lru_cache(maxsize=None)
def oede_flujos_hoja() -> pd.DataFrame:
    """Tabla 5 (sin estacionalidad) de la planilla de flujos más reciente publicada en la página de OEDE."""
    html = requests.get(PAGINA_OEDE, headers=CABECERAS, timeout=TIMEOUT).text
    enlaces = sorted(set(re.findall(r'(?:https://www\.argentina\.gob\.ar)?(/sites/default/files/flujos_de_creacion_y_destruccion_de_empleo[^"\']*\.xlsx)', html)))
    mejor, ultimo = None, None
    for e in enlaces:
        r = requests.get("https://www.argentina.gob.ar" + e, headers=CABECERAS, timeout=TIMEOUT)
        if r.status_code != 200 or r.content[:4] not in FIRMAS:
            continue
        df = pd.read_excel(io.BytesIO(r.content), sheet_name="T5", header=None)
        fechas = [f for f in (_trimestre_oede(_texto(v)) for v in df[0]) if f is not None]
        if fechas and (ultimo is None or max(fechas) > ultimo):
            mejor, ultimo = df, max(fechas)
    if mejor is None:
        raise RuntimeError("No se encontró la planilla de flujos de OEDE")
    return mejor


def _trimestre_oede(etiqueta: str) -> pd.Timestamp | None:
    m = re.match(r"([1-4])°\s*trim\.?\s*(\d{4})", etiqueta)
    return pd.Timestamp(int(m.group(2)), 3 * int(m.group(1)) - 2, 1) if m else None


def leer_oede(df: pd.DataFrame, campo: str) -> pd.Series:
    col = COLUMNAS_OEDE[campo]
    out = {}
    for i in range(len(df)):
        f = _trimestre_oede(_texto(df.iat[i, 0]))
        v = pd.to_numeric(df.iat[i, col], errors="coerce")
        if f is not None and pd.notna(v):
            out[f] = float(v)
    return pd.Series(out, dtype=float).sort_index()


def oede_empresas(campo: str) -> pd.Series:
    return leer_oede(oede_flujos_hoja(), campo)


LECTORES = {
    "oede_empresas": oede_empresas,
    "escribanos_compraventas": escribanos_compraventas,
    "bcra_pnfc": bcra_pnfc,
    "bcra_ib_lineas": bcra_ib_lineas,
    "indec_eph_ingresos": indec_eph_ingresos,
    "construya_indice": construya_indice,
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
