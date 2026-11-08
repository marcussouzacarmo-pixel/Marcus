"""Diagnóstico de sites de lojas: baixa páginas e grava HTML + cabeçalhos para análise.

Uso: python coletor/diagnostico.py  (lista de URLs em ALVOS)
Saída: diagnostico/<id>.html e diagnostico/resumo.json
"""
from __future__ import annotations

import gzip
import json
import urllib.error
import urllib.request
import zlib
from pathlib import Path

try:
    import brotli
except ImportError:
    brotli = None

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
ALVOS = {
    "mobly_moveis": "https://www.mobly.com.br/moveis",
    "mobly_sofas_p2": "https://www.mobly.com.br/moveis/sofas?page=2",
    "madeiramadeira_busca": "https://www.madeiramadeira.com.br/busca?q=sofa",
    "madeiramadeira_home": "https://www.madeiramadeira.com.br/",
    "tokstok_busca_s": "https://www.tokstok.com.br/s?q=sofa",
    "tokstok_busca_search": "https://www.tokstok.com.br/search?q=sofa",
    "tokstok_sofas": "https://www.tokstok.com.br/sofas",
}


def baixar(url: str) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9", "Accept-Encoding": "gzip, deflate" + (", br" if brotli else "")})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            corpo, status, cab, final = r.read(), r.status, {k.title(): v for k, v in r.headers.items()}, r.geturl()
    except urllib.error.HTTPError as e:
        corpo, status, cab, final = e.read(), e.code, {k.title(): v for k, v in e.headers.items()}, url
    except Exception as e:  # noqa: BLE001
        return {"url": url, "erro": f"{type(e).__name__}: {e}"}
    enc = (cab.get("Content-Encoding") or "").lower()
    try:
        if enc == "gzip":
            corpo = gzip.decompress(corpo)
        elif enc == "deflate":
            corpo = zlib.decompress(corpo)
        elif enc == "br" and brotli:
            corpo = brotli.decompress(corpo)
    except Exception:  # noqa: BLE001
        pass
    return {"url": url, "url_final": final, "status": status, "headers": cab,
            "tamanho": len(corpo), "texto": corpo.decode("utf-8", errors="replace")}


def main() -> None:
    pasta = Path("diagnostico")
    pasta.mkdir(exist_ok=True)
    resumo = {}
    for nome, url in ALVOS.items():
        r = baixar(url)
        texto = r.pop("texto", "")
        if texto:
            (pasta / f"{nome}.html").write_text(texto, encoding="utf-8")
        resumo[nome] = r
        print(nome, r.get("status"), r.get("tamanho"), r.get("erro", ""))
    (pasta / "resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
