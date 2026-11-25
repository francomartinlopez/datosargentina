"""Exploración: planillas del portal de datos de la Dirección de Estadística de Córdoba (CKAN)."""
from __future__ import annotations

import io
import traceback
from pathlib import Path

import pandas as pd
import requests

API = "https://datosestadistica.cba.gov.ar/api/3/action/package_show"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"}
CONJUNTOS = ["indic", "comercio-exterior", "pgb", "sector-industria", "indicadores-del-mercado-laboral"]


def main() -> None:
    out: list[str] = []
    p = out.append
    for c in CONJUNTOS:
        try:
            r0 = requests.get(API, params={"id": c}, headers=UA, timeout=60)
            p(f"== {c}: HTTP {r0.status_code} {r0.headers.get('content-type')} {r0.text[:200]!r}")
            res = r0.json()["result"]["resources"]
        except Exception:
            p(f"== {c}: " + traceback.format_exc()[-300:])
            Path("data").mkdir(exist_ok=True)
            Path("data/sondeo_cordoba.txt").write_text("\n".join(out), encoding="utf-8")
            continue
        for r in res:
            if (r.get("format") or "").upper() not in ("XLSX", "XLS"):
                continue
            if c == "indicadores-del-mercado-laboral" and "Gran Córdoba" not in r["name"]:
                continue
            p(f"\n===== {c} | {r['name']} | {r['url']}")
            try:
                b = requests.get(r["url"], headers=UA, timeout=120).content
                for h, df in list(pd.read_excel(io.BytesIO(b), sheet_name=None, header=None).items())[:4]:
                    p(f"-- hoja {h!r} {df.shape}")
                    p(df.head(14).to_string(max_colwidth=30, max_cols=12)[:3000])
                    p(df.tail(5).to_string(max_colwidth=30, max_cols=12)[:1500])
            except Exception:
                p(traceback.format_exc()[-300:])
        Path("data").mkdir(exist_ok=True)
        Path("data/sondeo_cordoba.txt").write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    main()
