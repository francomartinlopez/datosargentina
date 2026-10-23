"""Extractores: uno por tipo de fuente.

Cada extractor devuelve un pandas.Series con índice de fechas (Timestamp) y valores float,
ordenado y sin duplicados. La agregación a frecuencia mensual se hace después, en
pipeline.transformar.
"""
from __future__ import annotations

import time

import requests

TIMEOUT = (20, 120)
REINTENTOS = 3
CABECERAS = {"User-Agent": "datos-argentina/1.0 (+https://github.com)"}


def pedir(url: str, params: dict | None = None, verify: bool = True) -> requests.Response:
    """GET con reintentos y espera creciente. Lanza la última excepción si todos fallan."""
    ultimo_error: Exception | None = None
    for intento in range(REINTENTOS):
        try:
            r = requests.get(url, params=params, timeout=TIMEOUT, headers=CABECERAS, verify=verify)
            r.raise_for_status()
            return r
        except requests.RequestException as e:  # red, 5xx, 4xx
            ultimo_error = e
            time.sleep(2 ** intento)
    raise RuntimeError(f"No se pudo descargar {url}: {ultimo_error}")


def extraer(definicion: dict):
    """Despacha según el campo 'fuente' de la definición de la serie."""
    from . import argentinadatos, bcra, datosgobar, fred, manual

    fuentes = {
        "datosgobar": datosgobar.extraer,
        "bcra": bcra.extraer,
        "argentinadatos": argentinadatos.extraer,
        "fred": fred.extraer,
        "manual": manual.extraer,
    }
    tipo = definicion["fuente"]
    if tipo not in fuentes:
        raise ValueError(f"Fuente desconocida: {tipo}")
    return fuentes[tipo](definicion)
