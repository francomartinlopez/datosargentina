import pandas as pd
import pytest

from pipeline import transformar, vistas
from pipeline.fuentes import argentinadatos, bcra, datosgobar, fred


def mensual(valores, inicio="2020-01-01"):
    return pd.Series(valores, index=pd.date_range(inicio, periods=len(valores), freq="MS"), dtype=float)


# ---------- extractores: parseo de respuestas ----------

def test_parsear_datosgobar():
    s = datosgobar.parsear({"data": [["2026-07-01", 100.0], ["2026-08-01", None], ["2026-09-01", 102.5]]})
    assert list(s.values) == [100.0, 102.5]


def test_parsear_bcra_v4_y_v3():
    v4 = {"results": [{"idVariable": 1, "detalle": [{"fecha": "2026-10-20", "valor": 50153}, {"fecha": "2026-10-19", "valor": 50244}]}]}
    v3 = {"results": [{"idVariable": 1, "fecha": "2026-10-20", "valor": 50153}]}
    assert bcra.parsear(v4).index[0] == pd.Timestamp("2026-10-19")
    assert bcra.parsear(v3).iloc[0] == 50153


def test_parsear_argentinadatos_y_fred():
    s = argentinadatos.parsear([{"fecha": "2026-10-21", "valor": 674}], "valor")
    assert s.iloc[0] == 674
    f = fred.parsear("observation_date,CPIAUCSL\n2026-08-01,330.1\n2026-09-01,331.0\n", "CPIAUCSL")
    assert f.iloc[-1] == 331.0


# ---------- transformaciones ----------

def test_a_mensual_promedio_y_cierre():
    diaria = pd.Series([1.0, 3.0, 10.0], index=pd.to_datetime(["2026-01-05", "2026-01-20", "2026-02-02"]))
    assert transformar.a_mensual(diaria, "promedio").iloc[0] == 2.0
    assert transformar.a_mensual(diaria, "cierre").iloc[0] == 3.0


def test_empalme_respeta_variaciones_de_cada_tramo():
    viejo = mensual([100, 110, 121, 999, 999], "2020-01-01")       # 10% mensual hasta mar-2020
    nuevo = mensual([50, 51, 52.02, 53.0604, 54.1216], "2020-01-01")  # 2% mensual
    e = transformar.empalmar([(viejo, "2020-03-01"), (nuevo, None)])
    var = e.pct_change().dropna()
    assert var.loc["2020-02-01"] == pytest.approx(0.10)
    assert var.loc["2020-03-01"] == pytest.approx(0.10)
    assert var.loc["2020-04-01"] == pytest.approx(0.02)
    assert e.iloc[-1] == pytest.approx(nuevo.iloc[-1])  # nivel de la fuente vigente intacto


def test_empalme_detecta_huecos():
    a = mensual([100, 101], "2020-01-01")
    b = mensual([200, 202], "2020-06-01")
    with pytest.raises(ValueError):
        transformar.empalmar([(a, "2020-02-01"), (b, None)])


def test_moneda_constante():
    nominal = mensual([100, 200])
    ipc = mensual([1.0, 2.0])
    real = transformar.a_moneda_constante(nominal, ipc)
    assert list(real.values) == [200.0, 200.0]  # todo expresado en precios del último mes


def test_calculos():
    a, b = mensual([110, 120]), mensual([100, 100])
    assert list(transformar.calcular("brecha", a, b).round(6)) == [10.0, 20.0]
    assert list(transformar.calcular("resta", a, b)) == [10.0, 20.0]


# ---------- vistas ----------

def test_vistas_indice():
    s = mensual([100 * 1.01 ** i for i in range(60)], "2020-01-01")
    params = {"inicio_historico": "2020-06-01", "base_gestion_actual": "2023-11-01"}
    gestiones = [{"nombre": "A", "base": "2021-01-01"}, {"nombre": "B", "base": "2023-11-01"}]
    v = vistas.calcular_vistas(s, "indice", params, gestiones)
    assert v["intermensual"] == pytest.approx(1.0)
    assert v["interanual_ultimo"] == pytest.approx((1.01 ** 12 - 1) * 100)
    assert v["vistas"]["gestion_actual"][0] == ["2023-11-01", 100.0]
    assert v["vistas"]["comparativa"]["A"][0] == [0, 100.0]
    assert v["vistas"]["comparativa"]["A"][-1][0] == 34   # termina cuando empieza B


def test_vistas_tasa_en_puntos():
    s = mensual([7.0, 7.5, 8.0] + [8.0] * 9 + [6.0], "2022-12-01")
    params = {"inicio_historico": "2003-05-01", "base_gestion_actual": "2023-11-01"}
    v = vistas.calcular_vistas(s, "tasa", params, [])
    assert v["intermensual"] == pytest.approx(-2.0)
    assert v["interanual_ultimo"] == pytest.approx(-1.0)


def test_interanual_trimestral():
    s = pd.Series([10.0, 9.0, 8.0, 7.0, 6.0], index=pd.to_datetime(["2025-01-01", "2025-04-01", "2025-07-01", "2025-10-01", "2026-01-01"]))
    ia = vistas.interanual(s, "tasa")
    assert ia.loc["2026-01-01"] == pytest.approx(-4.0)
