"""Cuadros de valores: datos oficiales que no forman una serie de tiempo completa (por ejemplo, el
acumulado del año contra el mismo período del año anterior que publica un instituto provincial).

Cada cuadro es un JSON en data/manual/tablas/<id>.json:
{"id", "nombre", "seccion", "unidad", "periodo", "fecha", "fuente", "fuente_url", "nota",
 "columnas": [{"nombre", "tipo": "numero"|"porcentaje"|"texto", "decimales"}],
 "filas": [{"concepto", "nivel": 0|1, "celdas": [...]}]}
Salida: sitio/public/datos/tablas/<id>.json y tablas/indice.json.
"""
from __future__ import annotations

import json
from pathlib import Path

ORIGEN = Path(__file__).resolve().parents[1] / "data" / "manual" / "tablas"
TIPOS = {"numero", "porcentaje", "texto"}


def validar(t: dict) -> list[str]:
    err = [f"falta {k}" for k in ("id", "nombre", "seccion", "columnas", "filas", "fuente", "fecha") if not t.get(k)]
    if err:
        return err
    n = len(t["columnas"])
    for c in t["columnas"]:
        if c.get("tipo", "numero") not in TIPOS:
            err.append(f"tipo de columna desconocido: {c.get('tipo')}")
    for f in t["filas"]:
        if len(f.get("celdas", [])) != n:
            err.append(f"la fila «{f.get('concepto')}» tiene {len(f.get('celdas', []))} celdas y hay {n} columnas")
    return err


def construir(salida: Path) -> list[str]:
    alertas, ids = [], []
    destino = salida / "tablas"
    destino.mkdir(parents=True, exist_ok=True)
    for archivo in sorted(ORIGEN.glob("*.json")):
        try:
            t = json.loads(archivo.read_text(encoding="utf-8"))
        except Exception as e:
            alertas.append(f"Cuadro {archivo.name}: JSON inválido ({e})")
            continue
        err = validar(t)
        if err:
            alertas.append(f"Cuadro {archivo.name}: " + "; ".join(err))
            continue
        (destino / f"{t['id']}.json").write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
        ids.append(t["id"])
    for viejo in destino.glob("*.json"):  # cuadros que ya no están en data/manual/tablas
        if viejo.stem not in ids and viejo.name != "indice.json":
            viejo.unlink()
    (destino / "indice.json").write_text(json.dumps(ids), encoding="utf-8")
    return alertas
