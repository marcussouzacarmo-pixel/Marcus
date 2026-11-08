"""Conector para lojas em VTEX (APIs públicas de busca, sem autenticação).

Tenta, nesta ordem (ou só a definida em `api_vtex` no cadastro da loja):
  legado:      {base_url}/api/catalog_system/pub/products/search?ft=<termo>&_from=N&_to=M
  intelligent: {base_url}/api/io/_v/api/intelligent-search/product_search/?query=<termo>
Limite: 50 itens por página.
"""
from __future__ import annotations

import gzip
import json
import time
import zlib
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (compatible; ComparativoMoveis/1.0; monitoramento de precos)"
PAGINA = 50


def _get_json(url: str, timeout: float):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/json", "Accept-Encoding": "gzip, deflate"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        bruto = resp.read()
        enc = (resp.headers.get("Content-Encoding") or "").lower()
    if enc == "gzip" or bruto[:2] == b"\x1f\x8b":
        bruto = gzip.decompress(bruto)
    elif enc == "deflate":
        bruto = zlib.decompress(bruto)
    elif enc and enc != "identity":
        raise ValueError(f"compressão não suportada: {enc}")
    return json.loads(bruto.decode("utf-8"))


def _busca_legado(base: str, termo: str, ini: int, fim: int, extra: str, timeout: float) -> list:
    qs = urllib.parse.urlencode({"ft": termo, "_from": ini, "_to": fim})
    url = f"{base}/api/catalog_system/pub/products/search?{qs}" + (f"&{extra}" if extra else "")
    dados = _get_json(url, timeout)
    if not isinstance(dados, list):
        raise ValueError("resposta inesperada (não é lista) — loja pode não ser VTEX")
    return dados


def _busca_intelligent(base: str, termo: str, ini: int, fim: int, extra: str, timeout: float) -> list:
    """VTEX IO Intelligent Search (lojas que bloqueiam a API legada)."""
    qtd = fim - ini + 1
    qs = urllib.parse.urlencode({"query": termo, "page": ini // qtd + 1, "count": qtd, "locale": "pt-BR"})
    url = f"{base}/api/io/_v/api/intelligent-search/product_search/?{qs}" + (f"&{extra}" if extra else "")
    dados = _get_json(url, timeout)
    if not isinstance(dados, dict) or "products" not in dados:
        raise ValueError("resposta inesperada do Intelligent Search")
    return dados["products"]


MODOS = {"legado": _busca_legado, "intelligent": _busca_intelligent}


def _detectar_modo(base: str, extra: str, timeout: float, preferido: str | None) -> tuple[str, list[str]]:
    ordem = [preferido] if preferido else ["legado", "intelligent"]
    erros = []
    for modo in ordem:
        try:
            if MODOS[modo](base, "sofa", 0, 0, extra, timeout) is not None:
                return modo, erros
        except Exception as e:  # noqa: BLE001
            erros.append(f"API {modo}: {type(e).__name__}: {e}")
    raise RuntimeError("nenhuma API VTEX respondeu — " + " | ".join(erros))


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

    modo, avisos = _detectar_modo(base, extra, timeout, loja.get("api_vtex"))
    buscar = MODOS[modo]
    avisos.append(f"API utilizada: {modo}")
    por_sku: dict[str, dict] = {}
    falhas = 0
    total_termos = 0
    primeiro_erro = ""

    for categoria, termos in categorias.items():
        for termo in termos:
            total_termos += 1
            for ini in range(0, limite, PAGINA):
                fim = min(ini + PAGINA, limite) - 1
                try:
                    lote = buscar(base, termo, ini, fim, extra, timeout)
                except (urllib.error.URLError, ValueError, TimeoutError) as e:
                    falhas += 1
                    primeiro_erro = primeiro_erro or f"'{termo}': {e}"
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
        raise RuntimeError(f"todas as buscas falharam ({falhas}). Primeiro erro: {primeiro_erro}")
    return list(por_sku.values()), avisos[:20]
