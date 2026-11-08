"""Conector Mobly (Next.js): lê os produtos embutidos no payload da página de categoria.

A página traz, dentro de `self.__next_f.push([1,"..."])`, o objeto
`productsResponse` com `pagination` e `products` (nome, link, preços, estoque).

Preço usado: `unit_cash_price.price` (à vista no Pix), coerente com o "preço à
vista" das demais lojas; preço "de": `unit_original_price`.
Paginação: ?page=N até `pagination.last` ou `max_paginas`.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error

from coletor.plataformas.wake import _baixar  # mesmo cliente HTTP (gzip/br, UA de navegador)

RE_FLIGHT = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', re.S)
_DEC = json.JSONDecoder()


def _payload(pagina: str) -> str:
    return "".join(json.loads(f'"{c}"') for c in RE_FLIGHT.findall(pagina))


def extrair(pagina: str, categoria: str) -> tuple[list[dict], dict]:
    txt = _payload(pagina)
    i = txt.find('"productsResponse":')
    if i < 0:
        raise ValueError("productsResponse não encontrado (layout mudou?)")
    resp, _ = _DEC.raw_decode(txt, i + len('"productsResponse":'))
    regs = []
    for p in resp.get("products", []):
        cfg = p.get("configs") or {}
        preco_info = p.get("pricing") or {}
        vista = (preco_info.get("unit_cash_price") or {}).get("price") or preco_info.get("unit_special_price")
        if not vista or not cfg.get("id"):
            continue
        imgs = p.get("images") or [{}]
        nome = next((im.get("name") for im in imgs if im.get("name")), "")
        regs.append({
            "sku": str(cfg["id"]),
            "produto_id": str(cfg["id"]),
            "nome": nome,
            "marca": "",
            "categoria": categoria,
            "preco": round(float(vista), 2),
            "preco_lista": round(float(preco_info.get("unit_original_price") or 0), 2),
            "disponivel": int((p.get("stocks") or {}).get("quantity", 0) > 0),
            "url": (cfg.get("categoryLink") or "").split("?")[0],
            "imagem": (imgs[0].get("urls") or {}).get("catalog", ""),
        })
    return regs, resp.get("pagination") or {}


def coletar(loja: dict, _categorias: dict, params: dict) -> tuple[list[dict], list[str]]:
    base = loja["base_url"].rstrip("/")
    mapa: dict[str, list[str]] = loja.get("categorias_url") or {}
    if not mapa:
        raise ValueError("loja Mobly sem 'categorias_url' no cadastro")
    pausa = float(params.get("pausa_segundos", 1.0))
    timeout = float(params.get("timeout_segundos", 30))
    max_pag = int(loja.get("max_paginas", 3))

    por_sku: dict[str, dict] = {}
    avisos: list[str] = []
    falhas = total = 0
    for categoria, caminhos in mapa.items():
        for caminho in caminhos:
            total += 1
            for n in range(1, max_pag + 1):
                url = f"{base}{caminho}" + (f"?page={n}" if n > 1 else "")
                try:
                    regs, pag = extrair(_baixar(url, timeout), categoria)
                except (urllib.error.URLError, TimeoutError, ValueError) as e:
                    falhas += 1 if n == 1 else 0
                    avisos.append(f"{caminho} página {n}: {e}")
                    break
                finally:
                    time.sleep(pausa)
                novos = [r for r in regs if r["sku"] not in por_sku]
                for r in novos:
                    por_sku[r["sku"]] = r
                if not regs or int(pag.get("current", n)) >= int(pag.get("last", n)):
                    break
    if total and falhas >= total:
        raise RuntimeError(f"todas as categorias falharam. Primeiro erro: {avisos[0]}")
    if not por_sku:
        raise RuntimeError("nenhum produto lido — " + "; ".join(avisos[:3]))
    return list(por_sku.values()), avisos[:20]
