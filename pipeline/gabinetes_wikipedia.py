"""Exploración: tablas de los anexos de gabinetes en Wikipedia en español.

Busca las páginas "Anexo:Gabinete de ..." de los presidentes desde 2003, baja su HTML
y guarda cada tabla como CSV crudo en data/gabinetes/wikipedia/ para revisarlas.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "data" / "gabinetes" / "wikipedia"
API = "https://es.wikipedia.org/w/api.php"
CAB = {"User-Agent": "datos-argentina/1.0 (github.com/francomartinlopez/datosargentina)"}
PRESIDENTES = ["Néstor Kirchner", "Cristina Fernández de Kirchner", "Mauricio Macri", "Alberto Fernández", "Javier Milei"]


def buscar_paginas() -> dict[str, list[str]]:
    encontradas = {}
    for p in PRESIDENTES:
        r = requests.get(API, params={"action": "query", "list": "search", "srsearch": f"intitle:Gabinete {p}",
                                      "srnamespace": "0|104", "srlimit": 10, "format": "json"}, headers=CAB, timeout=60)
        r.raise_for_status()
        encontradas[p] = [x["title"] for x in r.json()["query"]["search"]]
    return encontradas


def tablas(titulo: str) -> list[pd.DataFrame]:
    r = requests.get(API, params={"action": "parse", "page": titulo, "prop": "text", "format": "json",
                                  "formatversion": 2}, headers=CAB, timeout=60)
    r.raise_for_status()
    html = r.json()["parse"]["text"]
    try:
        return pd.read_html(io.StringIO(html))
    except ValueError:
        return []


def main() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    paginas = buscar_paginas()
    (SALIDA / "paginas.json").write_text(json.dumps(paginas, ensure_ascii=False, indent=1), encoding="utf-8")
    for pres, titulos in paginas.items():
        for t in titulos:
            if "abinete" not in t:
                continue
            for i, df in enumerate(tablas(t)):
                if df.shape[0] < 3:
                    continue
                nombre = f"{t.replace(':', '_').replace(' ', '_').replace('/', '_')}__{i}.csv"
                df.to_csv(SALIDA / nombre, index=False)
    print(json.dumps(paginas, ensure_ascii=False))


if __name__ == "__main__":
    import traceback
    try:
        main()
    except Exception:
        SALIDA.mkdir(parents=True, exist_ok=True)
        (SALIDA / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        print(traceback.format_exc())
