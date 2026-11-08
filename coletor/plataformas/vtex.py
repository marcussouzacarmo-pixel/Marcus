"""Conector para lojas em VTEX (API pública de catálogo, sem autenticação).

Endpoint: {base_url}/api/catalog_system/pub/products/search?ft=<termo>&_from=N&_to=M
Limite da API: 50 itens por página.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (compatible; ComparativoMoveis/1.0; monitoramento de precos)"
PAGINA = 50


def _get(url: str, timeout: float) -> list:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        corpo = resp.read().decode("utf-8")
    dados = json.loads(corpo)
    if not isinstance(dados, list):
        raise ValueError("resposta inesperada (não é lista) — loja pode não ser VTEX")
    return dados


def _normalizar(prod: dict, categoria: str) -> list[dict]:
    """Um registro por SKU (item) com oferta do primeiro seller disponível."""
    regs = []
    for item in prod.get("items", []):
        sellers = item.get("sellers") or []
        oferta = None
        for s in sellers:
            co = s.get("commertialOffer") or {}
            if co.get("Price"):
                oferta = co
                if co.get("AvailableQuantity", 0) > 0:
                    break
        if not oferta:
            continue
        imgs = item.get("images") or []
        nome_item = item.get("nameComplete") or item.get("name") or ""
        regs.append({
            "sku": str(item.get("itemId", "")),
            "produto_id": str(prod.get("productId", "")),
            "nome": nome_item or prod.get("productName", ""),
            "marca": prod.get("brand", ""),
            "categoria": categoria,
            "preco": round(float(oferta.get("Price") or 0), 2),
            "preco_lista": round(float(oferta.get("ListPrice") or 0), 2),
            "disponivel": int(oferta.get("AvailableQuantity", 0) > 0),
            "url": prod.get("link", ""),
            "imagem": imgs[0].get("imageUrl", "") if imgs else "",
        })
    return regs


def coletar(loja: dict, categorias: dict[str, list[str]], params: dict) -> tuple[list[dict], list[str]]:
    base = loja["base_url"].rstrip("/")
    limite = int(params.get("itens_por_termo", 100))
    pausa = float(params.get("pausa_segundos", 1.0))
    timeout = float(params.get("timeout_segundos", 30))
    extra = loja.get("parametros_extra", "")  # ex.: "sc=1" ou "regionId=..."

    por_sku: dict[str, dict] = {}
    avisos: list[str] = []
    falhas = 0
    total_termos = 0

    for categoria, termos in categorias.items():
        for termo in termos:
            total_termos += 1
            for ini in range(0, limite, PAGINA):
                fim = min(ini + PAGINA, limite) - 1
                qs = urllib.parse.urlencode({"ft": termo, "_from": ini, "_to": fim})
                url = f"{base}/api/catalog_system/pub/products/search?{qs}" + (f"&{extra}" if extra else "")
                try:
                    lote = _get(url, timeout)
                except (urllib.error.URLError, ValueError, TimeoutError) as e:
                    falhas += 1
                    avisos.append(f"'{termo}' página {ini}: {e}")
                    break
                finally:
                    time.sleep(pausa)
                for prod in lote:
                    for r in _normalizar(prod, categoria):
                        # mesmo SKU pode aparecer em mais de um termo: mantém a 1ª categoria
                        por_sku.setdefault(r["sku"], r)
                if len(lote) < (fim - ini + 1):
                    break

    if falhas and falhas >= total_termos:
        raise RuntimeError(f"todas as buscas falharam ({falhas}). Primeiro erro: {avisos[0]}")
    return list(por_sku.values()), avisos[:20]
