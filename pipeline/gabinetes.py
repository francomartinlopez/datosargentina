"""Ministros y jefes de Gabinete de la Nación desde 2003, a partir de Wikidata.

Primera versión de la serie de rotación de gabinete. Wikidata registra cada cargo
(propiedad P39) con fecha de inicio (P580) y de fin (P582). La lista se revisa a mano
contra los decretos del Boletín Oficial antes de publicarse.

Uso:  python -m pipeline.gabinetes   -> data/gabinetes/ministros_wikidata.csv
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "data" / "gabinetes"
URL = "https://query.wikidata.org/sparql"

# Cargos ministeriales con jurisdicción Argentina (P1001 = Q414). Incluye jefe de Gabinete.
CONSULTA = """
SELECT DISTINCT ?persona ?personaLabel ?cargo ?cargoLabel ?inicio ?fin WHERE {
  ?cargo wdt:P1001 wd:Q414 .
  { ?cargo wdt:P31/wdt:P279* wd:Q83307 } UNION { ?cargo wdt:P279* wd:Q83307 }
  UNION { ?cargo wdt:P31/wdt:P279* wd:Q1501926 } UNION { ?cargo wdt:P279* wd:Q1501926 } .
  ?persona p:P39 ?st .
  ?st ps:P39 ?cargo ; pq:P580 ?inicio .
  OPTIONAL { ?st pq:P582 ?fin }
  FILTER(?inicio >= "2003-01-01T00:00:00Z"^^xsd:dateTime || (BOUND(?fin) && ?fin >= "2003-05-25T00:00:00Z"^^xsd:dateTime))
  SERVICE wikibase:label { bd:serviceParam wikibase:language "es,en". }
}
ORDER BY ?cargoLabel ?inicio
"""


def consultar() -> pd.DataFrame:
    r = requests.get(URL, params={"query": CONSULTA, "format": "json"},
                     headers={"User-Agent": "datos-argentina/1.0 (github.com/francomartinlopez/datosargentina)"},
                     timeout=(20, 180))
    r.raise_for_status()
    filas = []
    for b in r.json()["results"]["bindings"]:
        filas.append({
            "cargo": b["cargoLabel"]["value"],
            "persona": b["personaLabel"]["value"],
            "inicio": b["inicio"]["value"][:10],
            "fin": b.get("fin", {}).get("value", "")[:10],
            "wikidata_persona": b["persona"]["value"].rsplit("/", 1)[-1],
            "wikidata_cargo": b["cargo"]["value"].rsplit("/", 1)[-1],
        })
    return pd.DataFrame(filas).drop_duplicates()


def main() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    df = consultar()
    df.to_csv(SALIDA / "ministros_wikidata.csv", index=False)
    print(f"{len(df)} registros, {df['cargo'].nunique()} cargos")


if __name__ == "__main__":
    main()
