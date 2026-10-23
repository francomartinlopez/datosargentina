"""Exploración: textos de discursos presidenciales desde Wikisource, para relevar promesas."""
from __future__ import annotations

import re
import time
import traceback
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "data" / "discursos"
API = "https://es.wikisource.org/w/api.php"
CAB = {"User-Agent": "datos-argentina/1.0 (github.com/francomartinlopez/datosargentina)"}
PAGINAS = {
    "cfk_asuncion_2007": "Discurso de Cristina Fernández en el acto de asunción de la Presidencia",
    "cfk_asuncion_2011": "Discurso de Cristina Fernández en el acto de asunción de su segundo mandato como Presidenta de la Nación",
}


def texto(titulo: str) -> str:
    r = requests.get(API, params={"action": "parse", "page": titulo, "prop": "text", "format": "json",
                                  "formatversion": 2}, headers=CAB, timeout=60)
    r.raise_for_status()
    html = r.json()["parse"]["text"]
    plano = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", plano).strip()


def main() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    for clave, titulo in PAGINAS.items():
        (SALIDA / f"{clave}.txt").write_text(texto(titulo), encoding="utf-8")
        time.sleep(3)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        SALIDA.mkdir(parents=True, exist_ok=True)
        (SALIDA / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        print(traceback.format_exc())
