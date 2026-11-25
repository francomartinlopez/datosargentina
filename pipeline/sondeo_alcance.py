"""Exploración: ¿responden desde GitHub los sitios oficiales de minería y de las provincias? Con espera larga."""
from __future__ import annotations

import time
from pathlib import Path

import requests

from .fuentes import CABECERAS

URLS = ["https://www.mecon.gob.ar/dataset/Comercio/expominerales-siacam.csv",
        "http://www.mecon.gob.ar/dataset/Comercio/expominerales-siacam.csv",
        "https://www.estadisticasantafe.gob.ar/",
        "https://www.santafe.gob.ar/index.php/web/content/view/full/111738",
        "https://estadistica.cba.gov.ar/wp-json/wp/v2/media?search=IPC&per_page=20&_fields=source_url,date",
        "https://estadistica.cba.gov.ar/",
        "https://www.estadistica.ec.gba.gov.ar/dpe/",
        "https://www.estadisticaciudad.gob.ar/eyc/wp-json/wp/v2/media?search=IPCBA&per_page=50&_fields=source_url,date",
        "https://www.estadisticaciudad.gob.ar/eyc/wp-json/wp/v2/media?search=ETOI&per_page=50&_fields=source_url,date",
        "https://www.estadisticaciudad.gob.ar/eyc/wp-json/wp/v2/media?search=xlsx&per_page=100&_fields=source_url,date"]


def main() -> None:
    out = []
    for u in URLS:
        t = time.time()
        try:
            r = requests.get(u, headers=CABECERAS, timeout=(60, 120))
            out.append(f"== {u}\n  HTTP {r.status_code} {len(r.content)} bytes en {time.time()-t:.0f}s\n  {r.text[:3000]}")
        except Exception as e:
            out.append(f"== {u}\n  ERROR en {time.time()-t:.0f}s: {str(e)[:200]}")
        Path("data").mkdir(exist_ok=True)
        Path("data/sondeo_alcance.txt").write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    main()
