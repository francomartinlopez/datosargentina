import requests, pathlib, csv, io
t = requests.get("https://infra.datos.gob.ar/catalog/sspm/dataset/186/distribution/186.3/download/gasto-publico-programas-segurida-mensual.csv", timeout=60).text
rows = list(csv.reader(io.StringIO(t)))
out = [f"{h} = {v}" for h, v in zip(rows[0], rows[-1])]
pathlib.Path("data/meta186.txt").write_text("\n".join(out)); print("\n".join(out))
