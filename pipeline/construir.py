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

from . import calidad, distribucion, mapas, transformar, vistas
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
        if c["operacion"] == "combinacion":  # suma ponderada: {serie: coeficiente, ...}
            faltan = [x for x in c["terminos"] if x not in mensuales]
            if faltan:
                alertas.append(f"{nombre}: falta {', '.join(faltan)}, no se calcula")
                continue
            partes = pd.concat([mensuales[x] * k for x, k in c["terminos"].items()], axis=1, join="inner")
            mensuales[nombre] = partes.sum(axis=1)
            continue
        if c["operacion"] == "promedio":  # promedio simple de varias series (p. ej. deciles de un estrato)
            faltan = [x for x in c["series"] if x not in mensuales]
            if faltan:
                alertas.append(f"{nombre}: falta {', '.join(faltan)}, no se calcula")
                continue
            mensuales[nombre] = pd.concat([mensuales[x] for x in c["series"]], axis=1, join="inner").mean(axis=1)
            continue
        faltan = [x for x in (c["a"], c["b"]) if x not in mensuales]
        if faltan:
            alertas.append(f"{nombre}: falta {', '.join(faltan)}, no se calcula")
            continue
        mensuales[nombre] = transformar.calcular(c["operacion"], mensuales[c["a"]], mensuales[c["b"]])
    return mensuales, alertas


FUENTES_ARCHIVO = {"indec": "INDEC", "bcra": "BCRA", "finanzas": "Secretaría de Finanzas", "hacienda": "Secretaría de Hacienda"}


def nombre_fuente(definicion: dict) -> str:
    """Clave de fuente para el sitio; en las planillas se toma el organismo del lector (indec_..., finanzas_...)."""
    if not definicion:
        return "cálculo propio"
    if definicion.get("fuente") == "archivo":
        return FUENTES_ARCHIVO.get(definicion.get("lector", "").split("_")[0], "archivo")
    return definicion.get("fuente", "cálculo propio")


def preparar(nombre: str, ind: dict, mensuales: dict, deflactores: dict) -> pd.Series | None:
    """Serie lista para publicar: escala, moneda constante, acumulado de 12 meses y sin fechas futuras."""
    s = mensuales.get(nombre)
    if s is None or s.empty:
        return None
    if ind.get("escala"):
        s = s * ind["escala"]
    moneda = ind.get("moneda")
    if moneda:
        if deflactores.get(moneda) is None:
            return None
        s = transformar.a_moneda_constante(s, deflactores[moneda])
    if ind.get("acumulado_12m"):
        s = transformar.acumulado_12m(s)
    # algunas fuentes publican valores ya anunciados para meses futuros (p. ej. el salario mínimo)
    s = s[s.index <= pd.Timestamp.today().normalize()]
    return None if s.empty else s


def construir_indicadores(config: dict, mensuales: dict) -> tuple[list[dict], list[str]]:
    params, gestiones = config["parametros"], config["gestiones"]
    deflactores = {"ARS": mensuales.get("ipc"), "USD": mensuales.get("cpi_eeuu")}
    inicio = pd.Timestamp(params["inicio_historico"]) - pd.DateOffset(months=1)
    base = pd.Timestamp(params["base_gestion_actual"])
    fichas, alertas = [], []
    for ind in config["indicadores"]:
        s = preparar(ind["serie"], ind, mensuales, deflactores)
        if s is None:
            alertas.append(f"{ind['id']}: sin datos, no se publica")
            continue
        try:
            calc = vistas.calcular_vistas(s, ind["tipo_valor"], params, gestiones, ind.get("vista_historica", "nivel"))
        except Exception as e:  # un indicador con problemas no frena el resto
            alertas.append(f"{ind['id']}: error al calcular las vistas ({e}), no se publica")
            continue
        ficha = {
            "id": ind["id"], "nombre": ind["nombre"], "seccion": ind["seccion"], "unidad": ind["unidad"],
            "tipo_valor": ind["tipo_valor"], "frecuencia": ind.get("frecuencia", "M"),
            "fuente": nombre_fuente(config["series"].get(ind["serie"], {})),
            "nota": ind.get("nota", ""), "portada": bool(ind.get("portada")), "grupo": ind.get("grupo"),
            "ultimo": {"fecha": s.index[-1].strftime("%Y-%m-%d"), "valor": round(float(s.iloc[-1]), 4)},
            **calc,
            "_serie": vistas.como_lista(s[s.index >= inicio]),
        }
        # Serie desestacionalizada: la variación mensual se toma de ella y se dibuja junto a la original
        if ind.get("desestacionalizada"):
            d = preparar(ind["desestacionalizada"], ind, mensuales, deflactores)
            if d is None:
                alertas.append(f"{ind['id']}: falta la serie desestacionalizada")
            else:
                ficha["desest"] = {
                    "intermensual": vistas._finito(vistas.intermensual(d, ind["tipo_valor"])),
                    "fecha": d.index[-1].strftime("%Y-%m-%d"),
                    "gestion_actual": vistas.como_lista(d[d.index > base]),
                    "desde_2003": vistas.como_lista(d[d.index >= inicio]),
                }
        fichas.append(ficha)
    return fichas, alertas


def escribir(fichas: list[dict], mensuales: dict, alertas: list[str], config: dict | None = None) -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    PROCESADOS.mkdir(parents=True, exist_ok=True)
    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for f in fichas:
        f["actualizado"] = ahora
        serie = f.pop("_serie")
        (SALIDA / f"{f['id']}.json").write_text(json.dumps(f, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        # el CSV de descarga es la serie en nivel (moneda constante cuando corresponde), desde 2003
        pd.DataFrame(serie, columns=["fecha", "valor"]).to_csv(SALIDA / f"{f['id']}.csv", index=False)
    portada = [{k: f[k] for k in ("id", "nombre", "unidad", "ultimo", "intermensual", "interanual_ultimo")}
               for f in fichas if f["portada"]]
    # Los indicadores que forman parte de un grupo (p. ej. el EMAE por sector) se muestran
    # dentro de una sola ficha: el índice lleva la entrada del grupo en el lugar del primero.
    grupos = {g["id"]: g for g in (config or {}).get("grupos", [])}
    indice, vistos = [], set()
    for f in fichas:
        g = f.get("grupo")
        if not g:
            indice.append({k: f[k] for k in ("id", "nombre", "seccion")})
        elif g not in vistos and g in grupos:
            vistos.add(g)
            miembros = [x["id"] for x in fichas if x.get("grupo") == g]
            indice.append({"id": g, "nombre": grupos[g]["nombre"], "seccion": grupos[g]["seccion"], "tipo": "grupo",
                           "nota": grupos[g].get("nota", ""), "ranking": grupos[g].get("ranking", "variacion"),
                           "unidad_ranking": grupos[g].get("unidad_ranking", ""), "escala_ranking": grupos[g].get("escala_ranking", 1),
                           "sufijo_ranking": grupos[g].get("sufijo_ranking", " mil"), "miembros": miembros})
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
    alertas_mapas = [] if args.offline else mapas.construir(mensuales, config["parametros"], SALIDA) + distribucion.construir(SALIDA)
    escribir(fichas, mensuales, alertas + alertas_ind + alertas_mapas, config)
    print(f"Listo: {len(fichas)} indicadores, {len(alertas + alertas_ind + alertas_mapas)} alertas (ver data/informe.md)")


if __name__ == "__main__":
    main()
