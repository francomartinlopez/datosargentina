"""API de datos del INDEC (api.indec.gob.ar, en etapa beta).

Requiere un token personal en la variable de entorno INDEC_API_TOKEN (en GitHub, un secreto del
repositorio). Los servicios se consultan por PostgREST: filtros como parámetros (campo=eq.valor),
sumas en el servidor (select=campo,total:valor.sum()) y páginas de hasta 1000 filas.

Cada serie del YAML lleva fuente: indec_api, conjunto (qué lector usar) y campo (qué apertura).
"""
from __future__ import annotations

import os
from functools import lru_cache

import pandas as pd
import requests

from . import CABECERAS, TIMEOUT

URL = "https://api.indec.gob.ar/v1/"
PAGINA = 1000

# Unión Europea (27 miembros actuales) para agrupar el comercio exterior
UNION_EUROPEA = ["AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV",
                 "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"]
BLOQUES = {"china": ["CN"], "brasil": ["BR"], "estados_unidos": ["US"], "union_europea": UNION_EUROPEA,
           "chile": ["CL"], "india": ["IN"], "paraguay": ["PY"], "vietnam": ["VN"]}


def token() -> str:
    t = os.environ.get("INDEC_API_TOKEN", "").strip()
    if not t:
        raise RuntimeError("falta el token de la API del INDEC (INDEC_API_TOKEN)")
    return t


def consultar(conjunto: str, **params) -> list[dict]:
    """Todas las filas de una consulta, página por página."""
    cab = {**CABECERAS, "Authorization": f"Bearer {token()}"}
    filas, desde = [], 0
    while True:
        r = requests.get(URL + conjunto, params={**params, "limit": PAGINA, "offset": desde}, headers=cab, timeout=TIMEOUT)
        if r.status_code >= 400:
            raise RuntimeError(f"API INDEC {conjunto}: HTTP {r.status_code} {r.text[:200]}")
        lote = r.json()
        filas += lote
        if len(lote) < PAGINA:
            return filas
        desde += PAGINA


def fecha_periodo(p) -> pd.Timestamp:
    p = str(p)
    return pd.Timestamp(int(p[:4]), int(p[4:6]), 1)


def _serie(filas: list[dict], clave_fecha: str = "periodo", clave_valor: str = "valor") -> pd.Series:
    s = pd.Series({fecha_periodo(f[clave_fecha]): f[clave_valor] for f in filas if f.get(clave_valor) is not None}, dtype=float)
    return s.sort_index()


# ---------- Precios ----------

def ipc(campo: str) -> pd.Series:
    """campo 'región|código': índice del IPC (dic-16 = 100). Región: Nacional, GBA, Pampeana, Noreste,
    Noroeste, Cuyo, Patagonia. Código: 0 (nivel general), B/S (bienes/servicios), 04.1.1, etc."""
    region, codigo = campo.split("|")
    return _serie(consultar("ipc_nacional", select="periodo,valor", region=f"eq.{region}", codigo=f"eq.{codigo}",
                            tipo_de_indicador="eq.Indice", order="periodo.asc"))


def sipm(campo: str) -> pd.Series:
    """campo 'IPIM|NG', 'IPIB|NG' o 'IPP|NG': índices de precios mayoristas (dic-15 = 100)."""
    indicador, codigo = campo.split("|")
    return _serie(consultar("sipm_precios_mayoristas", select="periodo,valor", indicador=f"eq.{indicador}",
                            codigo_apertura=f"eq.{codigo}", tipo_de_indicador="eq.Indice", order="periodo.asc"))


def icc(campo: str = "0") -> pd.Series:
    """Índice del costo de la construcción en el GBA. campo: código de apertura (0 = nivel general,
    01 materiales, 02 mano de obra, 03 gastos generales)."""
    return _serie(consultar("icc_precios_construccion", select="periodo,valor", codigo_apertura=f"eq.{campo}",
                            tipo_de_indicador="eq.Indice", order="periodo.asc"))


# ---------- Producción ----------

def minero(campo: str) -> pd.Series:
    """campo 'tipo|descripción': p. ej. 'Índice|Nivel General - IPI Minero' o 'Unidades físicas|Carbonato de litio'."""
    tipo, descripcion = campo.split("|", 1)
    return _serie(consultar("ipi_minero", select="periodo,valor", tipo_de_indicador=f"eq.{tipo}",
                            descripcion=f"eq.{descripcion}", serie="eq.Serie Original", order="periodo.asc"))


# ---------- Canasta de crianza ----------

def crianza(campo: str) -> pd.Series:
    """Costo mensual de criar a un chico, en pesos corrientes. campo: tot_men1, tot_1a3, tot_4a5, tot_6a12
    (bys_ = bienes y servicios, cuid_ = tiempo de cuidado valorizado)."""
    return _serie(consultar("canasta-crianza", select=f"Periodo,{campo}", order="Periodo.asc"), "Periodo", campo)


# ---------- Comercio exterior ----------

@lru_cache(maxsize=None)
def _comercio(conjunto: str, campo_valor: str, apertura: str | None, desde: int = 2002) -> pd.DataFrame:
    """Suma mensual (US$) por país (apertura=None) o por otra columna (p. ej. uso_economico_cod),
    calculada en el servidor."""
    columna = apertura or "pais_cod"
    filas = consultar(conjunto, select=f"Periodo,{columna},v:{campo_valor}.sum()", Anio=f"gte.{desde}")
    df = pd.DataFrame(filas)
    df["fecha"] = df["Periodo"].map(fecha_periodo)
    return df.pivot_table(index="fecha", columns=columna, values="v", aggfunc="sum").sort_index()


def _por_bloque(df: pd.DataFrame, campo: str) -> pd.Series:
    """Millones de US$ por mes. 'resto' = total menos los bloques nombrados en BLOQUES."""
    total = df.sum(axis=1, min_count=1)
    if campo == "total":
        s = total
    elif campo == "resto":
        nombrados = [c for b in BLOQUES.values() for c in b if c in df.columns]
        s = total - df[nombrados].sum(axis=1, min_count=1).fillna(0)
    else:
        cols = [c for c in BLOQUES[campo] if c in df.columns]
        s = df[cols].sum(axis=1, min_count=1)
    return (s.dropna() / 1e6).sort_index()


def exportaciones(campo: str) -> pd.Series:
    """Exportaciones FOB por destino (bloque de BLOQUES, 'resto' o 'total'), millones de US$."""
    return _por_bloque(_comercio("comercio_exterior_exportacion_bienes", "valor_FOB", None), campo)


def importaciones(campo: str) -> pd.Series:
    """Importaciones CIF por origen (bloque de BLOQUES, 'resto' o 'total'), millones de US$."""
    return _por_bloque(_comercio("comercio_exterior_importacion_bienes", "valor_CIF", None), campo)


def importaciones_uso(campo: str) -> pd.Series:
    """Importaciones CIF por uso económico (código 1, 2, 3, 4, 5, 6 o 9), millones de US$."""
    df = _comercio("comercio_exterior_importacion_bienes", "valor_CIF", "uso_economico_cod")
    return (df[campo].dropna() / 1e6).sort_index() if campo in df.columns else pd.Series(dtype=float)


# ---------- Población ----------

@lru_cache(maxsize=None)
def poblacion_jurisdicciones() -> pd.DataFrame:
    """Población proyectada al 1° de julio de cada año (2022-2040), por jurisdicción (nombres del IGN)."""
    filas = consultar("proyecciones_poblacion_jurisdiccion_2022_2040", select="jurisdiccion_nom,fecha,total:poblacion.sum()")
    df = pd.DataFrame(filas)
    df["fecha"] = pd.to_datetime(df["fecha"].astype(str) + "-07-01")
    return df.pivot_table(index="fecha", columns="jurisdiccion_nom", values="total", aggfunc="sum").sort_index()


LECTORES = {"ipc": ipc, "sipm": sipm, "icc": icc, "minero": minero, "crianza": crianza,
            "exportaciones": exportaciones, "importaciones": importaciones, "importaciones_uso": importaciones_uso}


def extraer(definicion: dict) -> pd.Series:
    return LECTORES[definicion["conjunto"]](definicion.get("campo"))
