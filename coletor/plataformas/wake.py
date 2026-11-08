"""Conector para lojas na plataforma Wake Commerce (ex-Fbits) — ex.: Novo Mundo.

Lê as páginas de categoria públicas (HTML) e extrai os cards de produto:
  <div class=spot data-id=...> ... href=/produto/<slug>-<id> ... <h3>Nome</h3>
  <s>De: R$ x</s> (opcional) ... <b>R$ y</b>
Paginação: ?pagina=N (para quando a página repete itens ou vem vazia).
Respeita o robots.txt da loja (categorias e /produto são permitidos; /api/ não é usado).
"""
from __future__ import annotations

import gzip
import html
import re
import time
import urllib.error
import urllib.request
import zlib

try:
    import brotli
except ImportError:  # pragma: no cover
    brotli = None

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

RE_SPOT = re.compile(r"<div class=spot data-id=(\d+)>(.*?)(?=<div class=spot data-id=|<footer|$)", re.S)
RE_LINK = re.compile(r"href=\"?(/produto/[^\s\">]+)")
RE_NOME = re.compile(r"<h3>(.*?)</h3>", re.S)
RE_DE = re.compile(r"<s>\s*De:\s*R\$\s*([\d.,]+)\s*</s>")
RE_POR = re.compile(r"class=product__price-value>.*?<b>R\$\s*([\d.,]+)</b>", re.S)
RE_IMG = re.compile(r"<img[^>]+src=\"?([^\s\">]+)")


def _num(v: str) -> float:
    return round(float(v.replace(".", "").replace(",", ".")), 2)


def _baixar(url: str, timeout: float) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "text/html", "Accept-Language": "pt-BR,pt;q=0.9",
        "Accept-Encoding": "gzip, deflate" + (", br" if brotli else "")})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        bruto = r.read()
        enc = (r.headers.get("Content-Encoding") or "").lower()
    if enc == "gzip":
        bruto = gzip.decompress(bruto)
    elif enc == "deflate":
        bruto = zlib.decompress(bruto)
    elif enc == "br" and brotli:
        bruto = brotli.decompress(bruto)
    return bruto.decode("utf-8", errors="replace")


def extrair(pagina: str, base: str, categoria: str) -> list[dict]:
    regs = []
    for data_id, bloco in RE_SPOT.findall(pagina):
        link, nome, por = RE_LINK.search(bloco), RE_NOME.search(bloco), RE_POR.search(bloco)
        if not (link and nome and por):
            continue
        de, img = RE_DE.search(bloco), RE_IMG.search(bloco)
        slug = link.group(1)
        m_id = re.search(r"-(\d+)$", slug)
        regs.append({
            "sku": m_id.group(1) if m_id else data_id,
            "produto_id": data_id,
            "nome": html.unescape(re.sub(r"<[^>]+>", "", nome.group(1))).strip(),
            "marca": "",
            "categoria": categoria,
            "preco": _num(por.group(1)),
            "preco_lista": _num(de.group(1)) if de else 0.0,
            "disponivel": 1,  # a vitrine só lista itens com preço; indisponíveis não aparecem
            "url": base + slug,
            "imagem": img.group(1) if img else "",
        })
    return regs


def coletar(loja: dict, _categorias: dict, params: dict) -> tuple[list[dict], list[str]]:
    base = loja["base_url"].rstrip("/")
    mapa: dict[str, list[str]] = loja.get("categorias_url") or {}
    if not mapa:
        raise ValueError("loja Wake sem 'categorias_url' no cadastro")
    pausa = float(params.get("pausa_segundos", 1.0))
    timeout = float(params.get("timeout_segundos", 30))
    max_pag = int(loja.get("max_paginas", 10))

    por_sku: dict[str, dict] = {}
    avisos: list[str] = []
    falhas = total = 0
    for categoria, caminhos in mapa.items():
        for caminho in caminhos:
            total += 1
            vistos: set[str] = set()
            for n in range(1, max_pag + 1):
                url = f"{base}{caminho}" + (f"?pagina={n}" if n > 1 else "")
                try:
                    regs = extrair(_baixar(url, timeout), base, categoria)
                except (urllib.error.URLError, TimeoutError, ValueError) as e:
                    falhas += 1
                    avisos.append(f"{caminho} página {n}: {e}")
                    break
                finally:
                    time.sleep(pausa)
                novos = [r for r in regs if r["sku"] not in vistos]
                if not novos:
                    if n == 1:
                        avisos.append(f"{caminho}: nenhum produto lido (layout mudou?)")
                    break
                for r in novos:
                    vistos.add(r["sku"])
                    por_sku.setdefault(r["sku"], r)
    if total and falhas >= total:
        raise RuntimeError(f"todas as categorias falharam. Primeiro erro: {avisos[0]}")
    if not por_sku:
        raise RuntimeError("nenhum produto lido em nenhuma categoria — " + "; ".join(avisos[:3]))
    return list(por_sku.values()), avisos[:20]
