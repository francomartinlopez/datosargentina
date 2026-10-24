"""Control de diseño: que en la página no queden fichas solas en una fila.

En la computadora la grilla pone dos fichas por fila; los grupos (rankings) y las fichas
especiales (RIGI, mapas, encuestas, población) ocupan la fila entera. Entonces, en cada
sección, cada tramo de fichas comunes entre dos fichas anchas tiene que tener una cantidad par.
Las fichas especiales siempre van al final de su sección, así que el último tramo también
tiene que ser par.
"""
from __future__ import annotations


def huecos(config: dict, publicados: set[str] | None = None) -> list[str]:
    """publicados: ids que efectivamente se publicaron (un indicador sin datos no aparece y corre el resto)."""
    tramos: dict[str, list[list[str]]] = {}
    vistos = set()
    for ind in config["indicadores"]:
        if publicados is not None and ind["id"] not in publicados:
            continue
        sec = ind["seccion"]
        lista = tramos.setdefault(sec, [[]])
        g = ind.get("grupo")
        if g:
            if g not in vistos:  # el grupo se dibuja (ancho) donde aparece su primer miembro
                vistos.add(g)
                lista.append([])
            continue
        lista[-1].append(ind["id"])
    avisos = []
    for sec, lista in tramos.items():
        for tramo in lista:
            if len(tramo) % 2:
                avisos.append(f"Diseño: en «{sec}» queda una ficha sola en su fila (tramo de {len(tramo)} que termina en {tramo[-1]})")
    return avisos
