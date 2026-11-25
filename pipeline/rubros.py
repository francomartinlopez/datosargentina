"""Vista por rubro: agrupa indicadores que ya están en el sitio en seis rubros productivos.

La lista sale de la clave `rubros` de indicadores.yaml. Cada elemento es el id de un indicador,
"mapa:<id>" para un mapa provincial o "tabla:<id>" para un cuadro de valores. Un mismo indicador va en un solo rubro (los ids de las fichas son únicos en la página).
Salida: sitio/public/datos/rubros.json
"""
from __future__ import annotations

import json
from pathlib import Path


def construir(config: dict, fichas: list[dict], salida: Path) -> list[str]:
    publicados = {f["id"]: f for f in fichas if not f.get("variante_de")}
    carpeta_mapas = salida / "mapas"
    alertas, usados, rubros = [], set(), []
    for r in config.get("rubros", []):
        items = []
        for x in r["items"]:
            if x in usados:
                alertas.append(f"Rubros: {x} aparece en más de un rubro (queda en el primero)")
                continue
            if x.startswith("mapa:"):
                ok = (carpeta_mapas / f"{x[5:]}.json").exists()
                item = {"tipo": "mapa", "id": x[5:]}
            elif x.startswith("tabla:"):
                ok = (salida / "tablas" / f"{x[6:]}.json").exists()
                item = {"tipo": "tabla", "id": x[6:]}
            else:
                ok = x in publicados
                item = {"tipo": "indicador", "id": x}
            if not ok:
                alertas.append(f"Rubros: {x} (rubro {r['nombre']}) no está publicado")
                continue
            usados.add(x)
            items.append(item)
        rubros.append({"id": r["id"], "nombre": r["nombre"], "intro": r.get("intro", ""), "items": items})
    (salida / "rubros.json").write_text(json.dumps(rubros, ensure_ascii=False), encoding="utf-8")
    return alertas
