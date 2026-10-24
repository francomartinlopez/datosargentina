"""Exploración: baja archivos candidatos (Excel/CSV) y páginas índice para ver su estructura.

Para cada URL anota el código HTTP y el tamaño; los archivos que bajan bien se guardan en
data/archivos/ y, si son planillas, se resume cada hoja (primeras filas) en un .txt.
De las páginas HTML se extraen los enlaces a .xls/.xlsx/.csv.
"""
from __future__ import annotations

import io
import json
import re
import traceback
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "data" / "archivos"
CAB = {"User-Agent": "Mozilla/5.0 (datos-argentina; github.com/francomartinlopez/datosargentina)"}


def variantes_indec(patron: str, meses_atras: int = 14) -> list[str]:
    """Genera URLs con {MM}_{AA} para los últimos meses (INDEC nombra por mes de publicación)."""
    hoy = pd.Timestamp(date.today()).replace(day=1)
    out = []
    for k in range(meses_atras):
        f = hoy - pd.DateOffset(months=k)
        out.append(patron.format(MM=f"{f.month:02d}", AA=f"{f.year % 100:02d}", AAAA=f.year))
    return out


ARCHIVOS = {
    "came_pdf": ["https://www.redcame.org.ar/advf/documentos/2026/10/6ac2762cb873b.pdf"],
    "deuda_ult": ["https://www.argentina.gob.ar/sites/default/files/deuda_publica_30-06-2026.xlsx"],
    "eph_2026_1": ["https://www.indec.gob.ar/ftp/cuadros/menusuperior/eph/EPH_usu_1_Trim_2026_txt.zip", "https://www.indec.gob.ar/ftp/cuadros/menusuperior/eph/EPH_usu_1er_Trim_2026_txt.zip"],
    "eph_2026_2": ['https://www.indec.gob.ar/ftp/cuadros/menusuperior/eph/EPH_usu_2_Trim_2026_txt.zip', 'https://www.indec.gob.ar/ftp/cuadros/menusuperior/eph/EPH_usu_2do_Trim_2026_txt.zip'],
    "eph_2023_4": ['https://www.indec.gob.ar/ftp/cuadros/menusuperior/eph/EPH_usu_4_Trim_2023_txt.zip', 'https://www.indec.gob.ar/ftp/cuadros/menusuperior/eph/EPH_usu_4to_Trim_2023_txt.zip'],
    "eph_2017_1": ['https://www.indec.gob.ar/ftp/cuadros/menusuperior/eph/EPH_usu_1_Trim_2017_txt.zip', 'https://www.indec.gob.ar/ftp/cuadros/menusuperior/eph/EPH_usu_1er_Trim_2017_txt.zip', 'https://www.indec.gob.ar/ftp/cuadros/menusuperior/eph/EPH_usu_1er_Trim_2017.zip'],
    "zuban_ddd": ["https://zubancordoba.com/wp-content/uploads/2026/09/ZC-DDD-Septiembre.pdf"],
    "zuban_express": ["https://zubancordoba.com/wp-content/uploads/2026/09/DDD-EXPRESS-SEPTIEMBRE.pdf"],
    "espop_2610": ["https://images.udesa.edu.ar/sites/default/files/2026-10/56. UdeSA ESPOP Octubre 2026_0.pdf"],
    "atlas_2609": ["https://cdn1.atlasintel.org/ar_latam_pulse_atlas__bloomberg_09_2026_08821217ac86d7aa.pdf"],
    "atlas_2608": ["https://cdn1.atlasintel.org/ar_latam_pulse_atlas__bloomberg_08_2026_aa84843133a7af6c.pdf"],
    "bcra_ib_anexo": ["https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/informes/informe-bancos-anexo.xlsx"],
    "yahoo_merval": ["https://query1.finance.yahoo.com/v8/finance/chart/%5EMERV?range=max&interval=1mo"],
    "yahoo_ggal": ["https://query1.finance.yahoo.com/v8/finance/chart/GGAL?range=max&interval=1mo"],
    "byma": ["https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free/index-price"],
    "yahoo_ypf": ["https://query1.finance.yahoo.com/v8/finance/chart/YPF?range=max&interval=1mo"],
    "yahoo_argt": ["https://query1.finance.yahoo.com/v8/finance/chart/ARGT?range=max&interval=1mo"],
    "pnfc_series": ["https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/informes/Series-Report-Non-Financial-Credit-Providers-junio-2026.xlsx"],
    "pnfc_anexo": ["https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/informes/anexo-estadistico-proveedores-no-financieros-credito-junio-2026.xlsx"],
    "escribanos_comp": [f"https://www.colegio-escribanos.org.ar/noticias/{m}-Comparativo-anual-por-mes.xls" for m in ("Octubre-2025",)],
    "escribanos_nov": ["https://www.colegio-escribanos.org.ar/noticias/Noviembre-2025-Comparativo-anual-por-mes.xls"],
    "escribanos_dic": ["https://www.colegio-escribanos.org.ar/noticias/Diciembre-2025-Comparativo-anual-por-mes.xls"],
    "magyp_bovinos_ckan": ["https://datos.magyp.gob.ar/api/3/action/package_show?id=indicadores-mensuales-sector-bovino"],
    "magyp_aves_ckan": ["https://datos.magyp.gob.ar/api/3/action/package_show?id=consumo-de-carne-aviar"],
    "magyp_buscar_consumo": ["https://datos.magyp.gob.ar/api/3/action/package_search?q=consumo&rows=50"],
    "magyp_buscar_porcinos": ["https://datos.magyp.gob.ar/api/3/action/package_search?q=porcinos&rows=50"],
    "magyp_buscar_leche": ["https://datos.magyp.gob.ar/api/3/action/package_search?q=lacteo&rows=50"],
    "bov_anual": ["https://www.magyp.gob.ar/sitio/areas/bovinos/informacion_sectorial/_archivos/000030_Indicadores/000003-Indicadores%20bovinos%20anuales%201990-2023.pdf", "https://www.magyp.gob.ar/sitio/areas/bovinos/informacion_sectorial/_archivos/000030_Indicadores/000003-Indicadores%20bovinos%20anuales%201990-2024.pdf", "https://www.magyp.gob.ar/sitio/areas/bovinos/informacion_sectorial/_archivos/000030_Indicadores/000003-Indicadores%20bovinos%20anuales%201990-2025.pdf"],
    "bov_mensual": ["https://www.magyp.gob.ar/sitio/areas/bovinos/informacion_sectorial/_archivos/000030_Indicadores/000001-%20Indicadores%20bovinos%20al%20mes%20de%20SEPTIEMBRE%202026.pdf", "https://www.magyp.gob.ar/sitio/areas/bovinos/informacion_sectorial/_archivos/000030_Indicadores/000001-%20Indicadores%20bovinos%20al%20mes%20de%20AGOSTO%202026.pdf", "https://www.magyp.gob.ar/sitio/areas/bovinos/informacion_sectorial/_archivos/000030_Indicadores/000001-%20Indicadores%20bovinos%20al%20mes%20de%20JULIO%202026.pdf", "https://www.magyp.gob.ar/sitio/areas/bovinos/informacion_sectorial/_archivos/000030_Indicadores/000001-%20Indicadores%20bovinos%20al%20mes%20de%20FEBRERO%202026.pdf"],
    "carnes_pdf": ['https://www.argentina.gob.ar/sites/default/files/202610_consumo_per_capita_movil_carnes_vf.pdf', 'https://www.argentina.gob.ar/sites/default/files/202609_consumo_per_capita_movil_carnes_vf.pdf', 'https://www.argentina.gob.ar/sites/default/files/202608_consumo_per_capita_movil_carnes_vf.pdf', 'https://www.argentina.gob.ar/sites/default/files/202607_consumo_per_capita_movil_carnes_vf.pdf', 'https://www.argentina.gob.ar/sites/default/files/202606_consumo_per_capita_movil_carnes_vf.pdf', 'https://www.argentina.gob.ar/sites/default/files/202605_consumo_per_capita_movil_carnes_vf.pdf', 'https://www.argentina.gob.ar/sites/default/files/202604_consumo_per_capita_movil_carnes_vf.pdf', 'https://www.argentina.gob.ar/sites/default/files/202603_consumo_per_capita_movil_carnes_vf.pdf', 'https://www.argentina.gob.ar/sites/default/files/202602_consumo_per_capita_movil_carnes_vf.pdf', 'https://www.argentina.gob.ar/sites/default/files/202601_consumo_per_capita_movil_carnes_vf.pdf', 'https://www.argentina.gob.ar/sites/default/files/202610_consumo_per_capita_movil_carnes.pdf', 'https://www.argentina.gob.ar/sites/default/files/202609_consumo_per_capita_movil_carnes.pdf', 'https://www.argentina.gob.ar/sites/default/files/202608_consumo_per_capita_movil_carnes.pdf', 'https://www.argentina.gob.ar/sites/default/files/202607_consumo_per_capita_movil_carnes.pdf', 'https://www.argentina.gob.ar/sites/default/files/202606_consumo_per_capita_movil_carnes.pdf', 'https://www.argentina.gob.ar/sites/default/files/202605_consumo_per_capita_movil_carnes.pdf', 'https://www.argentina.gob.ar/sites/default/files/202604_consumo_per_capita_movil_carnes.pdf', 'https://www.argentina.gob.ar/sites/default/files/202603_consumo_per_capita_movil_carnes.pdf', 'https://www.argentina.gob.ar/sites/default/files/202602_consumo_per_capita_movil_carnes.pdf', 'https://www.argentina.gob.ar/sites/default/files/202601_consumo_per_capita_movil_carnes.pdf'],
    "owid_carnes": ["https://ourworldindata.org/grapher/per-capita-meat-type.csv?v=1&csvType=filtered&useColumnShortNames=true&country=~ARG"],
    "owid_leche": ["https://ourworldindata.org/grapher/per-capita-milk-consumption.csv?v=1&csvType=filtered&useColumnShortNames=true&country=~ARG"],
    "carnes_anual_2025": ["https://www.argentina.gob.ar/sites/default/files/000001_consumo_per_capita_de_carne_bovina_aviar_y_porcina_2025.pdf", "https://www.magyp.gob.ar/sitio/areas/bovinos/informacion_interes/informes/_archivos//000021=Consumo%20per%20capita%20de%20carne%20bovina,%20aviar%20y%20porcina/000001_Consumo%20per%20capita%20de%20carne%20bovina,%20aviar%20y%20porcina%202025.pdf"],
    "carnes_anual_2024": ["https://www.argentina.gob.ar/sites/default/files/000001_consumo_per_capita_de_carne_bovina_aviar_y_porcina_2024.pdf", "https://www.magyp.gob.ar/sitio/areas/bovinos/informacion_interes/informes/_archivos//000021=Consumo%20per%20capita%20de%20carne%20bovina,%20aviar%20y%20porcina/000001_Consumo%20per%20capita%20de%20carne%20bovina,%20aviar%20y%20porcina%202024.pdf"],
    "carnes_anual_2023": ["https://www.magyp.gob.ar/sitio/areas/bovinos/informacion_interes/informes/_archivos//000021=Consumo%20per%20capita%20de%20carne%20bovina,%20aviar%20y%20porcina/000001_Consumo%20per%20capita%20de%20carne%20bovina,%20aviar%20y%20porcina%202023.pdf", "https://www.magyp.gob.ar/sitio/areas/bovinos/informacion_interes/informes/_archivos//000021=Consumo%20per%20capita%20de%20carne%20bovina,%20aviar%20y%20porcina/000001_Consumo%20per%20capita%20de%20carne%20bovina,%20aviar%20y%20porcina%202022.pdf"],
    "carnes_pdf_2024": ["https://www.argentina.gob.ar/sites/default/files/202406_consumo_per_capita_movil_carnes_vf.pdf"],
    "oede_empresas": ["https://www.argentina.gob.ar/sites/default/files/nacional_serie_empresas_2.xlsx"],
    "oede_flujos0": ["https://www.argentina.gob.ar/sites/default/files/flujos_de_creacion_y_destruccion_de_empleo_0.xlsx"],
    "oede_flujos3": ["https://www.argentina.gob.ar/sites/default/files/flujos_de_creacion_y_destruccion_de_empleo_3.xlsx"],
    "bcra_series": ["https://www.bcra.gob.ar/Pdfs/PublicacionesEstadisticas/series.xlsm", "https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/series.xlsm"],
    "bcra_balance": ["https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/Balance_semanal.xls", "https://www.bcra.gob.ar/Pdfs/PublicacionesEstadisticas/balance.xls"],
    "bcra_balance_pdf": ["https://www.bcra.gob.ar/pdfs/publicacionesestadisticas/econ0200.pdf", "https://bcra.gob.ar/pdfs/publicacionesestadisticas/econ0200.pdf"],
    "rigi_dataset": ["https://docs.google.com/spreadsheets/d/1eytHJrzUjIFOXI-P1Hx_wbmZiSqPxVle059Djdos6u8/gviz/tq?tqx=out:csv&sheet=dataset"],
    "rigi_evaluacion": ["https://docs.google.com/spreadsheets/d/1eytHJrzUjIFOXI-P1Hx_wbmZiSqPxVle059Djdos6u8/gviz/tq?tqx=out:csv&sheet=evaluacion"],
    "ucii": variantes_indec("https://www.indec.gob.ar/ftp/cuadros/economia/capacidad_{MM}_{AA}.xls", 4) + ["https://www.indec.gob.ar/ftp/cuadros/economia/sh_capacidad_instalada.xls", "https://www.indec.gob.ar/ftp/cuadros/economia/cuadros_capacidad_instalada.xls"],
    "bcra_entidades": ["https://www.bcra.gob.ar/Pdfs/PublicacionesEstadisticas/entfin.xls", "https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/panhis.xls"],
}

PAGINAS = {
    "bcra_bancos": "https://www.bcra.gob.ar/PublicacionesEstadisticas/Informe_mensual_sobre_bancos.asp",
    "bcra_cambiario": "https://www.bcra.gob.ar/PublicacionesEstadisticas/Evolucion_del_mercado_de_cambios.asp",
    "bcra_series": "https://www.bcra.gob.ar/PublicacionesEstadisticas/Principales_variables_datos.asp",
    "indec_ucii": "https://www.indec.gob.ar/indec/web/Nivel4-Tema-3-6-22",
    "bcra_rem": "https://www.bcra.gob.ar/relevamiento-de-expectativas-de-mercado-rem/",
    "bcra_rem2": "https://www.bcra.gob.ar/PublicacionesEstadisticas/Relevamiento_Expectativas_de_Mercado.asp",
    "indec_eph_bases": "https://www.indec.gob.ar/indec/web/Institucional-Indec-BasesDeDatos",
    "magyp_bovinos": "https://www.magyp.gob.ar/sitio/areas/bovinos/informacion_sectorial/",
    "escribanos": "https://www.colegio-escribanos.org.ar/2025/11/26/cantidad-de-escrituras-de-compraventa-realizadas-en-octubre-2025/",
    "escribanos_cat": "https://www.colegio-escribanos.org.ar/category/estadisticas-de-escrituras/",
    "ocla_portafolio": "https://www.ocla.org.ar/portafolio/11/",
    "ocla_consumo": "https://ocla.org.ar/noticias/35452417-poblacion-y-consumo-domestico",
    "magyp_aves_carne": "https://www.magyp.gob.ar/sitio/areas/aves/estadistica/carne/index.php",
    "magyp_porcinos": "https://www.magyp.gob.ar/sitio/areas/porcinos/estadistica/",
    "bcra_estadisticas": "https://www.bcra.gob.ar/PublicacionesEstadisticas/Principales_variables.asp",
    "bcra_balances": "https://www.bcra.gob.ar/PublicacionesEstadisticas/Balances_semanales.asp",
    "bcra_series_pag": "https://www.bcra.gob.ar/PublicacionesEstadisticas/Planilla_series.asp",
    "oede_nacional": "https://www.argentina.gob.ar/trabajo/estadisticas/oede-estadisticas-nacionales",
    "oede_dinamica": "https://www.argentina.gob.ar/trabajo/estadisticas/empleo-y-dinamica-empresarial/dinamica-del-empleo-y-rotacion-de-empresas",
    "srt_cobertura": "https://www.srt.gob.ar/estadisticas/cobertura.php",
    "srt_estadisticas": "https://www.srt.gob.ar/index.php/estadisticas/",
    "seguridad_snic": "https://www.argentina.gob.ar/seguridad/estadisticascriminales/bases-de-datos",
}


def resumir_planilla(contenido: bytes, nombre: str) -> str:
    partes = []
    try:
        hojas = pd.read_excel(io.BytesIO(contenido), sheet_name=None, header=None)
    except Exception as e:
        return f"No se pudo leer como planilla: {e!r}"
    for hoja, df in hojas.items():
        partes.append(f"=== Hoja: {hoja} ({df.shape[0]} filas x {df.shape[1]} columnas)")
        partes.append(df.head(30).iloc[:, :14].to_string(max_colwidth=28))
        partes.append("... últimas filas:")
        partes.append(df.tail(6).iloc[:, :14].to_string(max_colwidth=28))
    return "\n".join(partes)


def main() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    informe = {}
    for clave, urls in ARCHIVOS.items():
        informe[clave] = []
        for u in urls:
            try:
                r = requests.get(u, headers=CAB, timeout=60)
                informe[clave].append({"url": u, "status": r.status_code, "bytes": len(r.content), "tipo": r.headers.get("content-type")})
                if r.status_code == 200 and "json" in (r.headers.get("content-type") or ""):
                    (SALIDA / f"{clave}.json").write_bytes(r.content[:400000])
                    break
                if r.status_code == 200 and len(r.content) > 500 and "html" not in (r.headers.get("content-type") or ""):
                    ext = "csv" if "csv" in (r.headers.get("content-type") or "") else u.rsplit(".", 1)[-1]
                    (SALIDA / f"{clave}.{ext}").write_bytes(r.content)
                    if ext in ("xls", "xlsx"):
                        (SALIDA / f"{clave}.txt").write_text(resumir_planilla(r.content, clave), encoding="utf-8")
                    else:
                        (SALIDA / f"{clave}.txt").write_text(r.content[:6000].decode("utf-8", "replace"), encoding="utf-8")
                    break
            except Exception as e:
                informe[clave].append({"url": u, "error": repr(e)})
    # páginas cuyo HTML se guarda crudo para buscar los datos que cargan por JavaScript
    for clave, u in {"construya3": "https://www.grupoconstruya.com.ar/servicios/indice_construya", "came_vm": "https://www.redcame.org.ar/estadisticas-pyme/78/ndice-de-ventas-minoristas",
                     "came_nota": "https://www.redcame.org.ar/novedades/574311162/las-ventas-minoristas-pyme-aumentaron-03-interanual-en-septiembre",
                     "construya": "https://www.grupoconstruya.com.ar/indice-construya", "construya2": "https://www.grupoconstruya.com.ar/",
                     "came_ventas": "https://www.redcame.org.ar/estadisticas-pyme", "came_home": "https://www.redcame.org.ar/",
                     "zuban_port": "https://zubancordoba.com/portfolio/informe-nacional-milei-vs-bullrich-septiembre-2026/", "zuban_port2": "https://zubancordoba.com/portfolio/informe-nacional-el-camino-al-balotaje-septiembre-2026/", "zuban_lista": "https://zubancordoba.com/portfolio-encuestas/", "udesa_espop": "https://udesa.edu.ar/espop", "udesa_espop2": "https://udesa.edu.ar/encuesta-de-satisfaccion-politica-y-opinion-publica",
                     "atlas_poll": "https://atlasintel.org/poll/latam-pulse-argentina-september-2026-2026-10-14",
                     "zuban": "https://zubancordoba.com/", "opina": "https://opinaargentina.com/", "poliarquia": "https://www.poliarquia.com/",
                     "mfit": "https://www.myfconsultora.com/", "analogias": "https://analogias.com.ar/", "giacobbe": "https://giacobbeyasociados.com/",
                     "dalessio": "https://www.dalessio.com.ar/", "rigi": "https://www.argentina.gob.ar/economia/rigi", "ocla_port": "https://www.ocla.org.ar/portafolio/11/",
                     "magyp_aves": "https://www.magyp.gob.ar/sitio/areas/aves/estadistica/carne/index.php",
                     "magyp_porc": "https://www.magyp.gob.ar/sitio/areas/porcinos/estadistica/",
                     "magyp_bov": "https://www.magyp.gob.ar/sitio/areas/bovinos/informacion_sectorial/indicadores/",
                     "magyp_aves_inf": "https://www.magyp.gob.ar/sitio/areas/aves/informes/",
                     "magyp_porc_inf": "https://www.magyp.gob.ar/sitio/areas/porcinos/informes/",
                     "agro_consumo": "https://www.argentina.gob.ar/agricultura/alimentos-y-bioeconomia/consumo-de-carnes"}.items():
        try:
            r = requests.get(u, headers=CAB, timeout=60)
            (SALIDA / f"{clave}.html").write_text(r.text[:600000], encoding="utf-8")
            for js in sorted(set(re.findall(r'(?:src|href)="([^"]+\.(?:js|json))"', r.text)))[:40]:
                if "rigi" in js.lower() or "proyecto" in js.lower():
                    c = requests.get(urljoin(u, js), headers=CAB, timeout=60)
                    (SALIDA / f"{clave}_{Path(js).name}").write_bytes(c.content[:600000])
        except Exception as e:
            (SALIDA / f"{clave}_error.txt").write_text(repr(e), encoding="utf-8")
    enlaces = {}
    for clave, u in PAGINAS.items():
        try:
            r = requests.get(u, headers=CAB, timeout=60)
            links = sorted(set(urljoin(u, h) for h in re.findall(r'href="([^"]+\.(?:xlsx?|csv|zip|xlsm))"', r.text, flags=re.I)))
            enlaces[clave] = {"status": r.status_code, "enlaces": links[:300]}
        except Exception as e:
            enlaces[clave] = {"error": repr(e)}
    # ejecuciones provinciales: el último archivo y el cuarto trimestre de 2023
    try:
        ej = [u for u in enlaces.get("ejecuciones", {}).get("enlaces", []) if "apnf" in u]
        for nombre, u in (("prov_ultimo", ej[-1] if ej else None), ("prov_2023", next((x for x in ej if "2023_-_trim._iv" in x), None))):
            if u:
                c = requests.get(u, headers=CAB, timeout=120).content
                ext = u.rsplit(".", 1)[-1]
                (SALIDA / f"{nombre}.{ext}").write_bytes(c)
                (SALIDA / f"{nombre}.txt").write_text(u + "\n" + resumir_planilla(c, nombre), encoding="utf-8")
    except Exception as e:
        (SALIDA / "prov_error.txt").write_text(repr(e), encoding="utf-8")
    # último archivo de deuda trimestral publicado
    try:
        cand = [u for u in enlaces.get("deuda", {}).get("enlaces", []) if re.search(r"deuda_publica_\d{2}-\d{2}-\d{4}", u)]
        def clave(u):
            d, m, a = re.search(r"deuda_publica_(\d{2})-(\d{2})-(\d{4})", u).groups()
            return (a, m, d)
        if cand:
            ult = sorted(cand, key=clave)[-1]
            r = requests.get(ult, headers=CAB, timeout=120)
            (SALIDA / "deuda.xlsx").write_bytes(r.content)
            (SALIDA / "deuda.txt").write_text(ult + "\n" + resumir_planilla(r.content, "deuda"), encoding="utf-8")
    except Exception as e:
        (SALIDA / "deuda_error.txt").write_text(repr(e), encoding="utf-8")
    (SALIDA / "informe.json").write_text(json.dumps({"archivos": informe, "paginas": enlaces}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        SALIDA.mkdir(parents=True, exist_ok=True)
        (SALIDA / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        print(traceback.format_exc())
