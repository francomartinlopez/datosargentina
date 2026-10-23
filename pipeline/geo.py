"""Exploración (se corre una vez): contorno simplificado de las provincias para los mapas.

Fuente: Instituto Geográfico Nacional (WFS, capa ign:provincia). Se recorta al territorio
continental e insular con datos estadísticos (sin el sector antártico) y se simplifica para
que el archivo pese poco en el sitio.

Salida: data/geo/provincias.json (GeoJSON con propiedades {nombre}).
"""
from __future__ import annotations

import json
import traceback
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "data" / "geo"
WFS = ("https://wms.ign.gob.ar/geoserver/ign/ows?service=WFS&version=1.0.0&request=GetFeature"
       "&typeName=ign:provincia&outputFormat=application/json")
CAB = {"User-Agent": "datos-argentina/1.0 (github.com/francomartinlopez/datosargentina)"}


def main() -> None:
    from shapely.geometry import box, mapping, shape

    SALIDA.mkdir(parents=True, exist_ok=True)
    gj = requests.get(WFS, headers=CAB, timeout=180).json()
    marco = box(-74.5, -55.2, -53.0, -21.5)  # continente, Tierra del Fuego y Malvinas
    features = []
    for f in gj["features"]:
        p = f["properties"]
        nombre = p.get("nam") or p.get("fna") or p.get("NAM")
        geom = shape(f["geometry"]).intersection(marco).simplify(0.02, preserve_topology=True)
        features.append({"type": "Feature", "properties": {"nombre": nombre, "codigo": p.get("in1")},
                         "geometry": json.loads(json.dumps(mapping(geom)), parse_float=lambda x: round(float(x), 3))})
    (SALIDA / "provincias.json").write_text(json.dumps({"type": "FeatureCollection", "features": features},
                                                       ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (SALIDA / "propiedades.json").write_text(json.dumps([f["properties"] for f in gj["features"]], ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        SALIDA.mkdir(parents=True, exist_ok=True)
        (SALIDA / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        print(traceback.format_exc())
