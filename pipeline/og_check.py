import re, requests, pathlib
U = "https://francomartinlopez.github.io/datosargentina/"
out = []
for ua in ["Twitterbot/1.0", "Mozilla/5.0"]:
    r = requests.get(U, headers={"User-Agent": ua}, timeout=30)
    out.append(f"{ua} {r.status_code} {r.headers.get('content-type')} len={len(r.text)}")
    out += re.findall(r'<meta[^>]+(?:og:|twitter:)[^>]+>', r.text)
for u in [U + "vista-previa.png", U + "?v=2"]:
    r = requests.get(u, headers={"User-Agent": "Twitterbot/1.0"}, timeout=30)
    out.append(f"{u} {r.status_code} {r.headers.get('content-type')} {len(r.content)}")
r = requests.get("http://francomartinlopez.github.io/datosargentina", headers={"User-Agent": "Twitterbot/1.0"}, timeout=30, allow_redirects=False)
out.append(f"sin barra {r.status_code} {r.headers.get('location')}")
pathlib.Path("data/og_check.txt").write_text("\n".join(out))
print("\n".join(out))
