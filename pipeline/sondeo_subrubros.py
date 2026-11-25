"""Exploración: exportaciones por subrubro (API del INDEC) y nomenclaturas, para separar la minería."""
from __future__ import annotations

import json
from pathlib import Path

from .fuentes.indec_api import consultar


def main() -> None:
    out = []
    try:
        filas = consultar("comercio_exterior_exportacion_bienes", select="rubro_cod,subrubro_cod,v:valor_FOB.sum(),kg:Peso_Neto.sum()",
                          Anio="eq.2025", order="subrubro_cod.asc")
        out += ["== exportaciones 2025 por subrubro"] + [json.dumps(f) for f in filas]
    except Exception as e:
        out.append(f"subrubros: {e}")
    try:
        nom = consultar("comercio_exterior_nomenclaturas", limit=5)
        out += ["== nomenclaturas (muestra)", json.dumps(nom[:5], ensure_ascii=False)]
        cols = list(nom[0]) if nom else []
        for c in cols:
            if "subrubro" in c.lower() or "rubro" in c.lower():
                todos = consultar("comercio_exterior_nomenclaturas", select=",".join(x for x in cols if "rubro" in x.lower()))
                vistos = sorted({json.dumps(t, ensure_ascii=False) for t in todos})
                out += [f"== combinaciones de rubro ({len(vistos)})"] + vistos[:400]
                break
    except Exception as e:
        out.append(f"nomenclaturas: {e}")
    Path("data").mkdir(exist_ok=True)
    Path("data/sondeo_subrubros.txt").write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    main()
