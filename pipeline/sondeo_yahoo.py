import requests, pathlib, json
out = []
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
for host in ["query1", "query2"]:
    for params in [{"range": "max", "interval": "1mo"}, {"range": "10y", "interval": "1mo"}, {"period1": "946684800", "period2": "1795000000", "interval": "1mo"}, {"range": "max", "interval": "1d"}]:
        try:
            r = requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/%5EMERV", params=params, headers=H, timeout=60)
            j = r.json(); res = (j.get("chart", {}).get("result") or [None])[0]
            if not res:
                out.append(f"{host} {params} {r.status_code} sin result {str(j)[:200]}"); continue
            ts = res.get("timestamp") or []
            q = res["indicators"]["quote"][0].get("close") or []
            out.append(f"{host} {params} {r.status_code} n_ts={len(ts)} n_close={sum(1 for x in q if x is not None)} meta.range={res['meta'].get('range')} validRanges={res['meta'].get('validRanges')} primero={ts[:1]}")
        except Exception as e:
            out.append(f"{host} {params} ERR {e}")
pathlib.Path("data/sondeo_yahoo.txt").write_text("\n".join(out)); print("\n".join(out))
