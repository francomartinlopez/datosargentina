"""Orquestador: baja las series, procesa y escribe los archivos para el sitio.

Uso:
    python -m pipeline.construir            # descarga todo y regenera
    python -m pipeline.construir --offline  # usa los datos crudos guardados (sin red)
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from . import calidad, transformar, vistas
from .fuentes import extraer

RAIZ = Path(__file__).resolve().parents[1]
CRUDOS = RAIZ / "data" / "crudos"
PROCESADOS = RAIZ / "data" / "procesados"
SALIDA = RAIZ / "sitio" / "public" / "datos"


def cargar_config() -> dict:
    with open(RAIZ / "indicadores.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def leer_crudo(nombre: str) -> pd.Series | None:
    ruta = CRUDOS / f"{nombre}.csv"
    if not ruta.exists():
        return None
    df = pd.read_csv(ruta, parse_dates=["fecha"])
    return pd.Series(df["valor"].values, index=df["fecha"], dtype=float)


def guardar_crudo(nombre: str, s: pd.Series) -> None:
    CRUDOS.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"fecha": s.index.strftime("%Y-%m-%d"), "valor": s.values}).to_csv(CRUDOS / f"{nombre}.csv", index=False)


def descargar(config: dict, offline: bool) -> tuple[dict, list[str]]:
    crudas, alertas = {}, []
    for nombre, definicion in config["series"].items():
        anterior = leer_crudo(nombre)
        if offline:
            if anterior is None:
                alertas.append(f"{nombre}: sin datos guardados")
                continue
            crudas[nombre] = anterior
            continue
        try:
            nueva = extraer(definicion)
            if nueva.empty:
                raise RuntimeError("respuesta vacía")
        except Exception as e:  # una fuente caída no frena el resto
            alertas.append(f"{nombre}: error al descargar ({e}); se conserva el dato anterior")
            if anterior is not None:
                crudas[nombre] = anterior
            continue
        alertas += calidad.revisar(nombre, transformar.a_mensual(nueva, definicion.get("agregacion", "promedio")),
                                   transformar.a_mensual(anterior, definicion.get("agregacion", "promedio")) if anterior is not None else None)
        guardar_crudo(nombre, nueva)
        crudas[nombre] = nueva
    return crudas, alertas


def procesar(config: dict, crudas: dict) -> tuple[dict[str, pd.Series], list[str]]:
    """Lleva todo a mensual y arma empalmes y cálculos. Si falta un insumo, el derivado
    se omite con una alerta en lugar de frenar la actualización."""
    alertas = []
    mensuales = {n: transformar.a_mensual(s, config["series"][n].get("agregacion", "promedio"))
                 for n, s in crudas.items()}
    for nombre, tramos in config.get("empalmes", {}).items():
        faltan = [t["serie"] for t in tramos if t["serie"] not in mensuales]
        if faltan:
            alertas.append(f"{nombre}: falta {', '.join(faltan)}, no se arma el empalme")
            continue
        mensuales[nombre] = transformar.empalmar([(mensuales[t["serie"]], t.get("hasta")) for t in tramos])
    for nombre, c in config.get("calculos", {}).items():
        faltan = [x for x in (c["a"], c["b"]) if x not in mensuales]
        if faltan:
            alertas.append(f"{nombre}: falta {', '.join(faltan)}, no se calcula")
            continue
        mensuales[nombre] = transformar.calcular(c["operacion"], mensuales[c["a"]], mensuales[c["b"]])
    return mensuales, alertas


def construir_indicadores(config: dict, mensuales: dict) -> tuple[list[dict], list[str]]:
    params, gestiones = config["parametros"], config["gestiones"]
    deflactores = {"ARS": mensuales.get("ipc"), "USD": mensuales.get("cpi_eeuu")}
    fichas, alertas = [], []
    for ind in config["indicadores"]:
        s = mensuales.get(ind["serie"])
        if s is None or s.empty:
            alertas.append(f"{ind['id']}: sin datos, no se publica")
            continue
        if ind.get("escala"):
            s = s * ind["escala"]
        moneda = ind.get("moneda")
        if moneda:
            if deflactores.get(moneda) is None:
                alertas.append(f"{ind['id']}: falta el deflactor {moneda}, no se publica")
                continue
            s = transformar.a_moneda_constante(s, deflactores[moneda])
        if ind.get("acumulado_12m"):
            s = transformar.acumulado_12m(s)
        # algunas fuentes publican valores ya anunciados para meses futuros (p. ej. el salario mínimo)
        s = s[s.index <= pd.Timestamp.today().normalize()]
        if s.empty:
            alertas.append(f"{ind['id']}: sin datos hasta hoy, no se publica")
            continue
        try:
            calc = vistas.calcular_vistas(s, ind["tipo_valor"], params, gestiones, ind.get("vista_historica", "nivel"))
        except Exception as e:  # un indicador con problemas no frena el resto
            alertas.append(f"{ind['id']}: error al calcular las vistas ({e}), no se publica")
            continue
        fichas.append({
            "id": ind["id"], "nombre": ind["nombre"], "seccion": ind["seccion"], "unidad": ind["unidad"],
            "tipo_valor": ind["tipo_valor"], "frecuencia": ind.get("frecuencia", "M"),
            "fuente": config["series"].get(ind["serie"], {}).get("fuente", "cálculo propio"),
            "nota": ind.get("nota", ""), "portada": bool(ind.get("portada")),
            "ultimo": {"fecha": s.index[-1].strftime("%Y-%m-%d"), "valor": round(float(s.iloc[-1]), 4)},
            **calc,
            "_serie": vistas.como_lista(s[s.index >= pd.Timestamp(params["inicio_historico"]) - pd.DateOffset(months=1)]),
        })
    return fichas, alertas


def escribir(fichas: list[dict], mensuales: dict, alertas: list[str]) -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    PROCESADOS.mkdir(parents=True, exist_ok=True)
    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for f in fichas:
        f["actualizado"] = ahora
        serie = f.pop("_serie")
        (SALIDA / f"{f['id']}.json").write_text(json.dumps(f, ensure_ascii=False), encoding="utf-8")
        # el CSV de descarga es la serie en nivel (moneda constante cuando corresponde), desde 2003
        pd.DataFrame(serie, columns=["fecha", "valor"]).to_csv(SALIDA / f"{f['id']}.csv", index=False)
    portada = [{k: f[k] for k in ("id", "nombre", "unidad", "ultimo", "intermensual", "interanual_ultimo")}
               for f in fichas if f["portada"]]
    indice = [{k: f[k] for k in ("id", "nombre", "seccion")} for f in fichas]
    (SALIDA / "portada.json").write_text(json.dumps(portada, ensure_ascii=False), encoding="utf-8")
    (SALIDA / "indice.json").write_text(json.dumps(indice, ensure_ascii=False), encoding="utf-8")
    largo = pd.concat([pd.DataFrame({"serie": n, "fecha": s.index, "valor": s.values}) for n, s in mensuales.items()])
    largo.to_parquet(PROCESADOS / "series.parquet", index=False)
    informe = [f"# Informe de actualización {ahora}", "", f"Indicadores publicados: {len(fichas)}", ""]
    informe += ["## Alertas", ""] + ([f"- {a}" for a in alertas] or ["- Sin alertas"])
    (RAIZ / "data" / "informe.md").write_text("\n".join(informe) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="usar datos crudos guardados")
    args = parser.parse_args()
    config = cargar_config()
    crudas, alertas = descargar(config, args.offline)
    mensuales, alertas_proc = procesar(config, crudas)
    alertas += alertas_proc
    fichas, alertas_ind = construir_indicadores(config, mensuales)
    escribir(fichas, mensuales, alertas + alertas_ind)
    print(f"Listo: {len(fichas)} indicadores, {len(alertas + alertas_ind)} alertas (ver data/informe.md)")


if __name__ == "__main__":
    main()
