"""Archivo de datos para la web de informes de Plexum: sitio/public/datos-informe.json.

Sigue la especificación «Datos que cada web publica para la web de informes de Plexum» (v1.3):
parte común y apartado 1 (Datos Argentina, Economía nacional). No cambia nada de lo que se ve en
el sitio: toma el último valor de indicadores que la web ya publica.

- indicadores: último valor de cada indicador del apartado (inflación, dólar oficial y CCL, EMAE,
  UCII, petróleo y gas, minería, salario y empleo registrados) y los datos por provincia que tiene
  la web (empleo y supermercados por provincia, IPC de la Ciudad, Santa Fe y Córdoba, desocupación y
  empleo por aglomerado, exportaciones de Córdoba y mineras de Santa Cruz y San Juan, PGB de Córdoba).
- agenda: publicaciones del INDEC de los próximos 60 días, leídas del calendario de difusión en PDF
  (con caché en data/derivados/calendario_indec.csv por si el INDEC no responde).
- faltantes: indicadores del apartado que esta vez no se publicaron.
"""
from __future__ import annotations

import calendar
import io
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "sitio" / "public" / "datos-informe.json"
CALENDARIO = RAIZ / "data" / "derivados" / "calendario_indec.csv"
CRUDOS = RAIZ / "data" / "crudos"
SITIO = "https://francomartinlopez.github.io/datosargentina/"
URL_CALENDARIO = "https://www.indec.gob.ar/indec/web/Calendario-Fecha-0"
ZONA = ZoneInfo("America/Argentina/Buenos_Aires")
WEB, EJE = "Datos Argentina", "Economía nacional"

RUBROS = {"Industria", "Agro", "Minería", "Energía", "Construcción", "Comercio y servicios"}
EXPOSICION = {"Exporta", "Importa insumos", "Deuda en dólares", "Energía intensiva", "Mano de obra intensiva",
              "Vende al Estado", "Vende a minería y energía"}
PROVINCIAS = {"Buenos Aires", "CABA", "Catamarca", "Chaco", "Chubut", "Córdoba", "Corrientes", "Entre Ríos", "Formosa",
              "Jujuy", "La Pampa", "La Rioja", "Mendoza", "Misiones", "Neuquén", "Río Negro", "Salta", "San Juan",
              "San Luis", "Santa Cruz", "Santa Fe", "Santiago del Estero", "Tierra del Fuego", "Tucumán"}
NIVELES = {"mundo", "país", "nacional", "provincia", "localidad"}
NOMBRE_PROVINCIA = {"Ciudad Autónoma de Buenos Aires": "CABA",
                    "Tierra del Fuego, Antártida e Islas del Atlántico Sur": "Tierra del Fuego"}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]

DOLAR = ["Exporta", "Importa insumos", "Deuda en dólares"]
MANO = ["Mano de obra intensiva"]
MINENER = ["Vende a minería y energía"]

# Indicadores del apartado: (id del informe, id de la ficha del sitio, nombre, medida, fuente, rubros, subrubros, exposición, alcance)
# medida: "nivel" (valor del último dato), "interanual" (variación % contra un año antes) o "mensual" (variación % contra el mes anterior)
NAC = ("nacional", "", "")
INDICADORES = [
    ("inflacion-mensual", "inflacion", "Inflación mensual (IPC)", "mensual", "INDEC", [], [], [], NAC),
    ("inflacion-interanual", "inflacion", "Inflación interanual (IPC)", "interanual", "INDEC", [], [], [], NAC),
    ("dolar-oficial-mayorista", "dolar_mayorista", "Dólar oficial mayorista", "diario", "BCRA (Comunicación A 3500)", [], [], DOLAR, NAC),
    ("dolar-ccl", "dolar_ccl", "Dólar contado con liquidación (paralelo financiero)", "diario", "Mercado (vía ArgentinaDatos)", [], [], DOLAR, NAC),
    ("emae", "emae", "Actividad económica (EMAE), variación interanual", "interanual", "INDEC", [], [], [], NAC),
    ("emae-industria", "emae_industria", "Actividad de la industria manufacturera (EMAE), variación interanual", "interanual", "INDEC", ["Industria"], [], [], NAC),
    ("emae-agro", "emae_agro", "Actividad del agro (EMAE), variación interanual", "interanual", "INDEC", ["Agro"], [], [], NAC),
    ("emae-mineria", "emae_mineria", "Actividad de minas y canteras (EMAE), variación interanual", "interanual", "INDEC", ["Minería", "Energía"], [], [], NAC),
    ("emae-energia", "emae_egu", "Actividad de electricidad, gas y agua (EMAE), variación interanual", "interanual", "INDEC", ["Energía"], [], [], NAC),
    ("emae-comercio", "emae_comercio", "Actividad del comercio (EMAE), variación interanual", "interanual", "INDEC", ["Comercio y servicios"], [], [], NAC),
    ("utilizacion-capacidad-industrial", "ucii", "Utilización de la capacidad instalada en la industria", "nivel", "INDEC", ["Industria"], [], [], NAC),
    ("produccion-petroleo", "produccion_petroleo", "Producción de petróleo", "nivel", "Secretaría de Energía", ["Energía"], ["petróleo y gas"], MINENER, NAC),
    ("produccion-petroleo-indice", "minero_petroleo", "Producción de petróleo crudo (IPI minero), variación interanual", "interanual", "INDEC", ["Energía"], ["petróleo y gas"], MINENER, NAC),
    ("produccion-gas", "produccion_gas", "Producción de gas natural", "nivel", "Secretaría de Energía", ["Energía"], ["petróleo y gas"], MINENER, NAC),
    ("produccion-gas-no-convencional", "gas_no_convencional", "Producción de gas no convencional (últimos 12 meses)", "nivel", "INDEC", ["Energía"], ["petróleo y gas"], MINENER, NAC),
    ("produccion-minera", "ipi_minero", "Producción minera e hidrocarburos (IPI minero), variación interanual", "interanual", "INDEC", ["Minería", "Energía"], [], MINENER, NAC),
    ("produccion-metaliferos", "metaliferos", "Producción de minerales metalíferos, variación interanual", "interanual", "INDEC", ["Minería"], ["minería metalífera"], MINENER, NAC),
    ("produccion-oro-plata", "oro_plata", "Producción de oro y plata (concentrados), variación interanual", "interanual", "INDEC", ["Minería"], ["oro y plata"], MINENER, NAC),
    ("produccion-litio", "litio_toneladas", "Producción de carbonato de litio (últimos 12 meses)", "nivel", "INDEC", ["Minería"], ["litio"], MINENER, NAC),
    ("exportaciones-mineras", "expo_mineras", "Exportaciones mineras (últimos 12 meses)", "nivel", "Secretaría de Minería", ["Minería"], [], ["Exporta"], NAC),
    ("salario-registrado-privado", "remuneracion_sipa", "Sueldo promedio privado registrado", "nivel", "SIPA (Ministerio de Capital Humano)", [], [], MANO, NAC),
    ("salario-registrado-privado-real", "salario_privado", "Salario real privado registrado (índice de salarios), variación interanual", "interanual", "INDEC", [], [], MANO, NAC),
    ("empleo-registrado-privado", "asalariados_privados", "Asalariados privados registrados", "nivel", "SIPA (Ministerio de Capital Humano)", [], [], MANO, NAC),
    ("empleo-registrado-industria", "empleo_industria", "Asalariados registrados en la industria manufacturera", "nivel", "SIPA (Ministerio de Capital Humano)", ["Industria"], [], MANO, NAC),
    ("empleo-registrado-agro", "empleo_agro", "Asalariados registrados en el agro", "nivel", "SIPA (Ministerio de Capital Humano)", ["Agro"], [], MANO, NAC),
    ("empleo-registrado-mineria", "empleo_mineria", "Asalariados registrados en minas y canteras", "nivel", "SIPA (Ministerio de Capital Humano)", ["Minería", "Energía"], [], MANO, NAC),
    ("empleo-registrado-energia", "empleo_egu", "Asalariados registrados en electricidad, gas y agua", "nivel", "SIPA (Ministerio de Capital Humano)", ["Energía"], [], MANO, NAC),
    ("empleo-registrado-construccion", "empleo_construccion", "Asalariados registrados en la construcción", "nivel", "SIPA (Ministerio de Capital Humano)", ["Construcción"], [], MANO, NAC),
    ("empleo-registrado-comercio", "empleo_comercio", "Asalariados registrados en el comercio", "nivel", "SIPA (Ministerio de Capital Humano)", ["Comercio y servicios"], [], MANO, NAC),
    # datos regionales
    ("inflacion-mensual-caba", "inflacion_caba", "Inflación mensual de la Ciudad de Buenos Aires (IPCBA)", "mensual", "Instituto de Estadística y Censos de la Ciudad de Buenos Aires", [], [], [], ("provincia", "CABA", "")),
    ("inflacion-interanual-caba", "inflacion_caba", "Inflación interanual de la Ciudad de Buenos Aires (IPCBA)", "interanual", "Instituto de Estadística y Censos de la Ciudad de Buenos Aires", [], [], [], ("provincia", "CABA", "")),
    ("inflacion-mensual-santa-fe", "ipc_santa_fe", "Inflación mensual de Santa Fe (IPEC)", "mensual", "IPEC Santa Fe", [], [], [], ("provincia", "Santa Fe", "")),
    ("inflacion-interanual-santa-fe", "ipc_santa_fe", "Inflación interanual de Santa Fe (IPEC)", "interanual", "IPEC Santa Fe", [], [], [], ("provincia", "Santa Fe", "")),
    ("inflacion-mensual-cordoba", "ipc_cordoba", "Inflación mensual de Córdoba (DGEyC)", "mensual", "Dirección General de Estadística y Censos de Córdoba", [], [], [], ("provincia", "Córdoba", "")),
    ("inflacion-interanual-cordoba", "ipc_cordoba", "Inflación interanual de Córdoba (DGEyC)", "interanual", "Dirección General de Estadística y Censos de Córdoba", [], [], [], ("provincia", "Córdoba", "")),
    ("desocupacion-gran-rosario", "desoc_regional", "Desocupación en Gran Rosario", "nivel", "INDEC (EPH, cálculo con microdatos)", [], [], [], ("localidad", "Santa Fe", "Gran Rosario")),
    ("desocupacion-gran-santa-fe", "eph_desoc_gran_santa_fe", "Desocupación en Gran Santa Fe", "nivel", "INDEC (EPH, cálculo con microdatos)", [], [], [], ("localidad", "Santa Fe", "Gran Santa Fe")),
    ("desocupacion-gran-cordoba", "eph_desoc_gran_cordoba", "Desocupación en Gran Córdoba", "nivel", "INDEC (EPH, cálculo con microdatos)", [], [], [], ("localidad", "Córdoba", "Gran Córdoba")),
    ("desocupacion-caba", "eph_desoc_caba", "Desocupación en la Ciudad de Buenos Aires", "nivel", "INDEC (EPH, cálculo con microdatos)", [], [], [], ("provincia", "CABA", "")),
    ("desocupacion-partidos-gba", "eph_desoc_partidos_gba", "Desocupación en los partidos del Gran Buenos Aires", "nivel", "INDEC (EPH, cálculo con microdatos)", [], [], [], ("localidad", "Buenos Aires", "Partidos del Gran Buenos Aires")),
    ("tasa-empleo-gran-rosario", "empleo_regional", "Tasa de empleo en Gran Rosario", "nivel", "INDEC (EPH, cálculo con microdatos)", [], [], [], ("localidad", "Santa Fe", "Gran Rosario")),
    ("tasa-empleo-gran-santa-fe", "eph_empleo_gran_santa_fe", "Tasa de empleo en Gran Santa Fe", "nivel", "INDEC (EPH, cálculo con microdatos)", [], [], [], ("localidad", "Santa Fe", "Gran Santa Fe")),
    ("tasa-empleo-gran-cordoba", "eph_empleo_gran_cordoba", "Tasa de empleo en Gran Córdoba", "nivel", "INDEC (EPH, cálculo con microdatos)", [], [], [], ("localidad", "Córdoba", "Gran Córdoba")),
    ("tasa-empleo-caba", "eph_empleo_caba", "Tasa de empleo en la Ciudad de Buenos Aires", "nivel", "INDEC (EPH, cálculo con microdatos)", [], [], [], ("provincia", "CABA", "")),
    ("tasa-empleo-partidos-gba", "eph_empleo_partidos_gba", "Tasa de empleo en los partidos del Gran Buenos Aires", "nivel", "INDEC (EPH, cálculo con microdatos)", [], [], [], ("localidad", "Buenos Aires", "Partidos del Gran Buenos Aires")),
    ("exportaciones-cordoba", "expo_cordoba", "Exportaciones de Córdoba (últimos 12 meses)", "nivel", "Dirección General de Estadística y Censos de Córdoba", [], [], ["Exporta"], ("provincia", "Córdoba", "")),
    ("exportaciones-cordoba-primarios", "expo_cordoba_pp", "Exportaciones de Córdoba: productos primarios (últimos 12 meses)", "nivel", "Dirección General de Estadística y Censos de Córdoba", ["Agro"], [], ["Exporta"], ("provincia", "Córdoba", "")),
    ("exportaciones-cordoba-moa", "expo_cordoba_moa", "Exportaciones de Córdoba: manufacturas de origen agropecuario (últimos 12 meses)", "nivel", "Dirección General de Estadística y Censos de Córdoba", ["Agro", "Industria"], ["agroindustria"], ["Exporta"], ("provincia", "Córdoba", "")),
    ("exportaciones-cordoba-moi", "expo_cordoba_moi", "Exportaciones de Córdoba: manufacturas de origen industrial (últimos 12 meses)", "nivel", "Dirección General de Estadística y Censos de Córdoba", ["Industria"], [], ["Exporta"], ("provincia", "Córdoba", "")),
    ("exportaciones-cordoba-energia", "expo_cordoba_cye", "Exportaciones de Córdoba: combustibles y energía (últimos 12 meses)", "nivel", "Dirección General de Estadística y Censos de Córdoba", ["Energía"], [], ["Exporta"], ("provincia", "Córdoba", "")),
    ("pgb-cordoba", "pgb_cordoba", "Producto geográfico bruto de Córdoba", "nivel", "Dirección General de Estadística y Censos de Córdoba", [], [], [], ("provincia", "Córdoba", "")),
    ("exportaciones-mineras-santa-cruz", "expo_mineria_santa_cruz", "Exportaciones mineras de Santa Cruz (últimos 12 meses)", "nivel", "Secretaría de Minería", ["Minería"], [], ["Exporta"], ("provincia", "Santa Cruz", "")),
    ("exportaciones-mineras-san-juan", "expo_mineria_san_juan", "Exportaciones mineras de San Juan (últimos 12 meses)", "nivel", "Secretaría de Minería", ["Minería"], [], ["Exporta"], ("provincia", "San Juan", "")),
]

# Mapas por provincia que publica la web: (prefijo del id, archivo, nombre, unidad, fuente, rubros, exposición)
MAPAS = [
    ("empleo-registrado-privado", "empleo_provincias", "Asalariados privados registrados", "miles de personas",
     "SIPA (Ministerio de Capital Humano)", [], MANO),
    ("ventas-supermercados", "supermercados_provincias", "Ventas en supermercados", "millones de pesos de hoy por mes",
     "INDEC, Encuesta de supermercados", ["Comercio y servicios"], []),
]

# Lo que pide el apartado y la web no muestra: va siempre en faltantes
NO_PUBLICADOS = [
    ("utilizacion-capacidad-industrial-bloques", "Utilización de la capacidad industrial por bloque",
     "La web publica solo el nivel general de la UCII; no muestra la apertura por bloque"),
    ("tarifa-electrica-industrial", "Tarifa eléctrica industrial", "La web no publica la tarifa eléctrica industrial"),
]

# Grupos (v1.3): el mismo dato abierto por rubro u otra dimensión. id del indicador → (grupo, nombre, dimensión, clave)
def _g(gid, nombre, dim, miembros):
    return {i: (gid, nombre, dim, c) for i, c in miembros.items()}


GRUPOS = {
    **_g("emae-por-rubro", "Actividad económica por rubro (EMAE)", "rubro",
         {"emae-industria": "Industria", "emae-agro": "Agro", "emae-mineria": "Minería", "emae-energia": "Energía",
          "emae-comercio": "Comercio y servicios"}),
    **_g("empleo-registrado-por-rubro", "Asalariados registrados por rubro", "rubro",
         {"empleo-registrado-industria": "Industria", "empleo-registrado-agro": "Agro", "empleo-registrado-mineria": "Minería",
          "empleo-registrado-energia": "Energía", "empleo-registrado-construccion": "Construcción",
          "empleo-registrado-comercio": "Comercio y servicios"}),
    **_g("desocupacion-por-aglomerado", "Desocupación por aglomerado", "otro",
         {"desocupacion-gran-rosario": "Gran Rosario", "desocupacion-gran-santa-fe": "Gran Santa Fe",
          "desocupacion-gran-cordoba": "Gran Córdoba", "desocupacion-caba": "Ciudad de Buenos Aires",
          "desocupacion-partidos-gba": "Partidos del Gran Buenos Aires"}),
    **_g("tasa-empleo-por-aglomerado", "Tasa de empleo por aglomerado", "otro",
         {"tasa-empleo-gran-rosario": "Gran Rosario", "tasa-empleo-gran-santa-fe": "Gran Santa Fe",
          "tasa-empleo-gran-cordoba": "Gran Córdoba", "tasa-empleo-caba": "Ciudad de Buenos Aires",
          "tasa-empleo-partidos-gba": "Partidos del Gran Buenos Aires"}),
    **_g("exportaciones-cordoba-por-rubro", "Exportaciones de Córdoba por gran rubro", "otro",
         {"exportaciones-cordoba-primarios": "productos primarios", "exportaciones-cordoba-moa": "manufacturas de origen agropecuario",
          "exportaciones-cordoba-moi": "manufacturas de origen industrial", "exportaciones-cordoba-energia": "combustibles y energía"}),
    **_g("inflacion-mensual-por-provincia", "Inflación mensual por provincia", "provincia",
         {"inflacion-mensual-caba": "CABA", "inflacion-mensual-santa-fe": "Santa Fe", "inflacion-mensual-cordoba": "Córdoba"}),
    **_g("inflacion-interanual-por-provincia", "Inflación interanual por provincia", "provincia",
         {"inflacion-interanual-caba": "CABA", "inflacion-interanual-santa-fe": "Santa Fe", "inflacion-interanual-cordoba": "Córdoba"}),
}


def armar_grupos(indicadores: list[dict]) -> list[str]:
    """Asigna los grupos. Un grupo necesita 3 o más miembros con la misma unidad y la misma fecha del dato:
    los que quedan atrasados salen del grupo (siguen como indicador suelto) y el grupo se arma con el resto."""
    for r in indicadores:
        if r["id"] in GRUPOS:
            gid, nombre, dim, clave = GRUPOS[r["id"]]
            r["grupo"] = {"id": gid, "nombre": nombre, "dimension": dim, "clave": clave}
    avisos, por_grupo = [], {}
    for r in indicadores:
        if r.get("grupo"):
            por_grupo.setdefault(r["grupo"]["id"], []).append(r)
    for gid, miembros in por_grupo.items():
        comun = max(pd.Series([(m["fecha_dato"], m["unidad"]) for m in miembros]).value_counts().items(), key=lambda x: (x[1], x[0]))[0]
        dentro = [m for m in miembros if (m["fecha_dato"], m["unidad"]) == comun]
        for m in miembros:
            if m not in dentro or len(dentro) < 3:
                m.pop("grupo")
        if len(dentro) < 3:
            avisos.append(f"grupo {gid}: menos de 3 miembros con la misma fecha, no se arma")
        elif len(dentro) < len(miembros):
            avisos.append(f"grupo {gid}: {len(miembros) - len(dentro)} miembro(s) con otra fecha quedan fuera")
    return avisos


# Publicaciones del INDEC que van en la agenda: (texto con que empieza el título, nombre corto, rubros)
AGENDA = [
    ("Índice de precios al consumidor (IPC)", "Inflación (IPC)", []),
    ("Estimador mensual de actividad económica", "Actividad económica (EMAE)", []),
    ("Utilización de la capacidad instalada", "Utilización de la capacidad industrial (UCII)", ["Industria"]),
    ("Índice de producción industrial manufacturero", "Producción industrial (IPI manufacturero)", ["Industria"]),
    ("Índice de producción industrial minero", "Producción minera e hidrocarburos (IPI minero)", ["Minería", "Energía"]),
    ("Indicadores de coyuntura de la actividad de la construcción", "Actividad de la construcción (ISAC)", ["Construcción"]),
    ("Índice del costo de la construcción", "Costo de la construcción (ICC)", ["Construcción"]),
    ("Índice de salarios", "Índice de salarios", []),
    ("Sistema de índices de precios mayoristas", "Precios mayoristas (SIPM)", []),
    ("Intercambio comercial argentino", "Comercio exterior (ICA)", []),
    ("Encuesta de supermercados", "Ventas en supermercados", ["Comercio y servicios"]),
    ("Informe de avance del nivel de actividad", "PIB trimestral", []),
    ("Mercado de trabajo. Tasas e indicadores", "Mercado de trabajo (EPH)", []),
    ("Valorización mensual de la canasta básica", "Canasta básica alimentaria y total", []),
    ("Incidencia de la pobreza", "Pobreza e indigencia", []),
    ("Origen provincial de las exportaciones", "Exportaciones por provincia", []),
    ("Balanza de pagos", "Balanza de pagos", []),
]


def _num(x: float, dec: int = 2) -> float:
    return round(float(x), dec)


def fin_periodo(fecha: str, frecuencia: str) -> pd.Timestamp:
    """Fecha del dato: último día del mes, del trimestre o del año."""
    f = pd.Timestamp(fecha)
    if frecuencia == "T":
        f = f + pd.DateOffset(months=2)
    elif frecuencia == "A":
        f = pd.Timestamp(f.year, 12, 1)
    return pd.Timestamp(f.year, f.month, calendar.monthrange(f.year, f.month)[1])


def periodo(fecha: str, frecuencia: str) -> str | None:
    f = pd.Timestamp(fecha)
    if frecuencia == "T":
        return f"{f.year}-T{(f.month - 1) // 3 + 1}"
    if frecuencia == "M":
        return f.strftime("%Y-%m")
    return None


def _alcance(a: tuple) -> dict:
    return {"nivel": a[0], "provincia": a[1], "localidad": a[2], "pais": "Argentina"}


def _contra(frecuencia: str) -> str:
    return {"T": "mismo trimestre del año anterior", "A": "año anterior"}.get(frecuencia, "mismo mes del año anterior")


def _anterior(frecuencia: str) -> str:
    return "trimestre anterior" if frecuencia == "T" else "mes anterior"


def _serie(ficha: dict) -> pd.Series:
    datos = ficha.get("_serie") or []
    return pd.Series([v for _, v in datos], index=pd.to_datetime([f for f, _ in datos]), dtype=float).dropna()


def _var_pct(s: pd.Series, meses: int) -> pd.Series:
    previo = s.copy()
    previo.index = previo.index + pd.DateOffset(months=meses)
    a, b = s.align(previo, join="inner")
    return (a / b - 1) * 100


FRECUENCIAS = {"M": "mensual", "T": "trimestral", "A": "anual", "D": "diaria"}
LARGO = {"M": 25, "T": 9, "A": 10, "D": 25}  # puntos de la serie (v1.3)


def _lista(s: pd.Series, frec: str, dec: int) -> list[dict]:
    """Serie para el informe: del más viejo al más nuevo, con la fecha del dato (fin del período o día real)."""
    s = s.dropna().iloc[-LARGO[frec]:]
    fechas = s.index if frec == "D" else [fin_periodo(f.strftime("%Y-%m-%d"), frec) for f in s.index]
    return [{"fecha": f.strftime("%Y-%m-%d"), "valor": _num(v, dec)} for f, v in zip(fechas, s.values)]


def _comparar(frec: str, puntos: int, acumulado: bool) -> list[str]:
    if frec in ("M", "D"):
        if puntos >= 13:
            return ["interanual"] if acumulado else ["mensual", "interanual"]
        return [] if acumulado or puntos < 2 else ["mensual"]
    if frec == "T":
        return ["interanual"] if puntos >= 5 else []
    return ["interanual"] if puntos >= 2 else []


def _v13(r: dict, s: pd.Series, frec: str, dec: int, acumulado: bool = False) -> dict:
    """Agrega los campos de la versión 1.3 y toma el valor y la fecha del último punto de la serie."""
    serie = _lista(s, frec, dec)
    r["valor"], r["fecha_dato"] = serie[-1]["valor"], serie[-1]["fecha"]
    r["tipo_valor"] = "tasa" if r["unidad"].startswith("%") else "nivel"
    r["frecuencia"] = FRECUENCIAS[frec]
    r["comparar"] = _comparar(frec, len(serie), acumulado)
    r["serie"] = serie
    return r


def _dolar(nombre_crudo: str) -> tuple[pd.Series, float | None] | None:
    """Cotizaciones diarias (última de cada mes) y variación del último dato contra el promedio del mes anterior."""
    ruta = CRUDOS / f"{nombre_crudo}.csv"
    if not ruta.exists():
        return None
    df = pd.read_csv(ruta, parse_dates=["fecha"]).dropna()
    if df.empty:
        return None
    ultimo = df.iloc[-1]
    mes_previo = (ultimo["fecha"].to_period("M") - 1)
    previo = df[df["fecha"].dt.to_period("M") == mes_previo]["valor"]
    var = (ultimo["valor"] / previo.mean() - 1) * 100 if len(previo) else None
    cierres = df.groupby(df["fecha"].dt.to_period("M")).tail(1)
    return pd.Series(cierres["valor"].values, index=pd.DatetimeIndex(cierres["fecha"]), dtype=float), var


def indicador(entrada: tuple, fichas: dict) -> dict | None:
    iid, fid, nombre, medida, fuente, rubros, subrubros, expo, alcance = entrada
    f = fichas.get(fid)
    if f is None:
        return None
    frec = f.get("frecuencia", "M")
    base = {"id": iid, "nombre": nombre}
    if medida == "diario":
        d = _dolar(fid)
        if d is None:
            return None
        cierres, var = d
        base["unidad"] = "pesos por dólar"
        if var is not None:
            base["variacion"] = {"valor": _num(var, 1), "unidad": "%", "contra": "promedio del mes anterior"}
        _v13(base, cierres, "D", 2)
        base["periodo"] = base["fecha_dato"][:7]
    else:
        s = _serie(f)
        if s.empty or s.index[-1] != pd.Timestamp(f["ultimo"]["fecha"]):
            return None
        meses = 3 if frec == "T" else 12 if frec == "A" else 1
        if medida == "mensual":
            m = _var_pct(s, 1).dropna()
            if len(m) < 2:
                return None
            base["unidad"] = "%"
            base["variacion"] = {"valor": _num(m.iloc[-1] - m.iloc[-2], 1), "unidad": "p. p.", "contra": "mes anterior"}
            _v13(base, m, frec, 1)
        elif medida == "interanual":
            ia = _var_pct(s, 12).dropna()
            if ia.empty or ia.index[-1] != s.index[-1]:
                return None
            base["unidad"] = "% interanual"
            if len(ia) >= 2:
                base["variacion"] = {"valor": _num(ia.iloc[-1] - ia.iloc[-2], 1), "unidad": "p. p.", "contra": _anterior(frec)}
            _v13(base, ia, frec, 1)
        else:
            tasa = f["tipo_valor"] in ("tasa", "porcentaje")
            base["unidad"] = f["unidad"]
            if f.get("interanual_ultimo") is not None:
                base["variacion"] = {"valor": _num(f["interanual_ultimo"], 1), "unidad": "p. p." if tasa else "%", "contra": _contra(frec)}
            if frec == "T":
                s = s[s.index.month.isin([1, 4, 7, 10])]
            _v13(base, s, frec, 1 if tasa else 2, acumulado="últimos 12 meses" in f["unidad"])
        p = periodo(f["ultimo"]["fecha"], frec)
        if p:
            base["periodo"] = p
    base.update(fuente_original=fuente, eje=EJE, alcance=_alcance(alcance), rubros=rubros, subrubros=subrubros,
                exposicion=expo, url=SITIO)
    return base


def _slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def por_provincia(carpeta_mapas: Path) -> list[dict]:
    out = []
    for prefijo, archivo, nombre, unidad, fuente, rubros, expo in MAPAS:
        ruta = carpeta_mapas / f"{archivo}.json"
        if not ruta.exists():
            continue
        m = json.loads(ruta.read_text(encoding="utf-8"))
        for prov, datos in (m.get("provincias") or {}).items():
            prov = NOMBRE_PROVINCIA.get(prov, prov)
            if prov not in PROVINCIAS or not datos:
                continue
            s = pd.Series([v for _, v in datos], index=pd.to_datetime([f for f, _ in datos]), dtype=float).dropna()
            if s.empty:
                continue
            ia = _var_pct(s, 12).dropna()
            r = {"id": f"{prefijo}-{_slug(prov)}", "nombre": f"{nombre}: {prov}", "unidad": unidad}
            if len(ia) and ia.index[-1] == s.index[-1]:
                r["variacion"] = {"valor": _num(ia.iloc[-1], 1), "unidad": "%", "contra": "mismo mes del año anterior"}
            _v13(r, s, "M", 2)
            r.update(periodo=s.index[-1].strftime("%Y-%m"), fuente_original=fuente, eje=EJE,
                     alcance=_alcance(("provincia", prov, "")), rubros=rubros, subrubros=[], exposicion=expo, url=SITIO,
                     grupo={"id": f"{prefijo}-por-provincia", "nombre": f"{nombre} por provincia", "dimension": "provincia", "clave": prov})
            out.append(r)
    return out


# ---------- agenda: calendario de difusión del INDEC ----------

def leer_calendario_pdf(contenido: bytes, anio: int) -> list[dict]:
    """Eventos (fecha, título) de un calendario semestral del INDEC en PDF."""
    from pypdf import PdfReader
    texto = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(contenido)).pages)
    mes, dia, eventos = None, None, []
    for linea in texto.splitlines():
        linea = linea.strip()
        if linea.lower() in MESES:
            mes, dia = MESES.index(linea.lower()) + 1, None
            continue
        m = re.match(r"^(\d{1,2}) (LU|MA|MI|JU|VI|SA|DO) (.+)$", linea)
        if m:
            dia, linea = int(m.group(1)), m.group(3)
        if mes and dia and linea:
            eventos.append({"fecha": f"{anio}-{mes:02d}-{dia:02d}", "titulo": linea.strip()})
    return eventos


def actualizar_calendario(offline: bool) -> pd.DataFrame:
    previo = pd.read_csv(CALENDARIO) if CALENDARIO.exists() else pd.DataFrame(columns=["fecha", "titulo"])
    if offline:
        return previo
    import requests
    hoy = datetime.now(ZONA)
    semestres = {(hoy.year, 1 if hoy.month <= 6 else 2)}
    semestres.add((hoy.year + 1, 1) if hoy.month > 6 else (hoy.year, 2))
    nuevos = []
    for anio, sem in sorted(semestres):
        url = f"https://www.indec.gob.ar/ftp/cuadros/publicaciones/calendario_{sem}sem{anio}.pdf"
        try:
            r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
            if r.ok and r.content[:4] == b"%PDF":
                nuevos += leer_calendario_pdf(r.content, anio)
        except Exception:
            pass  # el calendario es opcional: se usa el guardado
    if not nuevos:
        return previo
    df = pd.DataFrame(nuevos)
    # lo recién leído reemplaza los meses que cubre; se conservan los meses viejos del caché
    meses = set(df["fecha"].str[:7])
    df = pd.concat([previo[~previo["fecha"].astype(str).str[:7].isin(meses)], df]).drop_duplicates().sort_values(["fecha", "titulo"])
    CALENDARIO.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CALENDARIO, index=False)
    return df


def agenda(calendario: pd.DataFrame, hoy: pd.Timestamp) -> list[dict]:
    out = []
    limite = hoy + pd.Timedelta(days=60)
    for _, e in calendario.iterrows():
        fecha = pd.Timestamp(e["fecha"])
        if not (hoy <= fecha <= limite):
            continue
        for inicio, corto, rubros in AGENDA:
            if str(e["titulo"]).startswith(inicio):
                per = str(e["titulo"]).rstrip(". ").rsplit(". ", 1)[-1].lower()
                de = "del" if per.startswith(("primer", "segundo", "tercer", "cuarto")) else "de"
                out.append({"fecha": fecha.strftime("%Y-%m-%d"), "evento": f"{corto}: dato {de} {per} (INDEC)", "eje": EJE,
                            "alcance": _alcance(NAC), "rubros": rubros, "url": URL_CALENDARIO})
                break
    return out


# ---------- armado ----------

def validar(doc: dict) -> list[str]:
    err = []
    ids = [i["id"] for i in doc["indicadores"]]
    if len(ids) != len(set(ids)):
        err.append("ids de indicadores repetidos")
    for r in doc["indicadores"] + doc["agenda"]:
        a = r["alcance"]
        if a["nivel"] not in NIVELES or (a["provincia"] and a["provincia"] not in PROVINCIAS):
            err.append(f"alcance inválido en {r.get('id') or r.get('evento')}")
        if not set(r["rubros"]) <= RUBROS:
            err.append(f"rubro inválido en {r.get('id') or r.get('evento')}")
        if r["eje"] != EJE:
            err.append(f"eje inválido en {r.get('id') or r.get('evento')}")
    for r in doc["indicadores"]:
        if not set(r["exposicion"]) <= EXPOSICION:
            err.append(f"exposición inválida en {r['id']}")
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", r["id"]):
            err.append(f"id con formato inválido: {r['id']}")
        if r["valor"] is None or (isinstance(r["valor"], float) and r["valor"] != r["valor"]):
            err.append(f"valor vacío en {r['id']}")
        serie = r.get("serie") or []
        if serie and (serie[-1]["valor"] != r["valor"] or serie[-1]["fecha"] != r["fecha_dato"]):
            err.append(f"la serie de {r['id']} no termina en el valor publicado")
        if [x["fecha"] for x in serie] != sorted({x["fecha"] for x in serie}):
            err.append(f"fechas desordenadas o repetidas en la serie de {r['id']}")
        if r.get("tipo_valor") not in ("tasa", "nivel", "estado") or r.get("frecuencia") not in FRECUENCIAS.values():
            err.append(f"tipo_valor o frecuencia inválidos en {r['id']}")
        if not set(r.get("comparar", [None])) <= {"mensual", "interanual"}:
            err.append(f"comparar inválido en {r['id']}")
        g = r.get("grupo")
        if g and g["dimension"] == "provincia" and g["clave"] not in PROVINCIAS:
            err.append(f"clave de provincia inválida en {r['id']}")
        if g and g["dimension"] == "rubro" and g["clave"] not in RUBROS:
            err.append(f"clave de rubro inválida en {r['id']}")
    return err


def construir(fichas: list[dict], carpeta_mapas: Path, offline: bool = False, ahora: datetime | None = None,
              calendario: pd.DataFrame | None = None, destino: Path = DESTINO) -> list[str]:
    ahora = ahora or datetime.now(ZONA)
    por_id = {f["id"]: f for f in fichas}
    previo = {}
    if destino.exists():
        try:
            anterior = json.loads(destino.read_text(encoding="utf-8"))
            previo = {i["id"]: i["fecha_dato"] for i in anterior.get("indicadores", [])}
            previo.update({i["id"]: i.get("ultimo_dato") for i in anterior.get("faltantes", []) if i["id"] not in previo})
        except Exception:
            pass
    indicadores, faltantes = [], []
    for e in INDICADORES:
        r = indicador(e, por_id)
        if r is None:
            faltantes.append({"id": e[0], "nombre": e[2], "motivo": "La fuente no respondió o no hubo dato en esta actualización",
                              "ultimo_dato": previo.get(e[0])})
        else:
            indicadores.append(r)
    indicadores += por_provincia(carpeta_mapas)
    avisos = armar_grupos(indicadores)
    faltantes += [{"id": i, "nombre": n, "motivo": m, "ultimo_dato": None} for i, n, m in NO_PUBLICADOS]
    if calendario is None:
        calendario = actualizar_calendario(offline)
    doc = {"web": WEB, "version": "1.3", "generado": ahora.isoformat(timespec="seconds"),
           "indicadores": indicadores, "novedades": [],
           "agenda": agenda(calendario, pd.Timestamp(ahora.date())), "faltantes": faltantes}
    alertas = [f"datos-informe.json: {e}" for e in validar(doc) + avisos]
    destino.write_text(json.dumps(doc, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    if not doc["agenda"]:
        alertas.append("datos-informe.json: la agenda quedó vacía (no se pudo leer el calendario del INDEC)")
    return alertas
