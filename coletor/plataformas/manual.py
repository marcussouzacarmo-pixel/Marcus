"""Conector para lojas sem e-commerce: lê data/manual/<loja_id>.csv.

Colunas obrigatórias: sku;nome;categoria;preco
Opcionais: marca;preco_lista;disponivel;url
Separador ';' e decimal com vírgula (padrão Excel pt-BR) ou ponto.
O preço informado é registrado com a data da coleta — atualize o CSV sempre que houver nova pesquisa.
"""
from __future__ import annotations

import csv
from pathlib import Path


def _num(v: str) -> float:
    v = (v or "").strip().replace("R$", "").replace(" ", "")
    if "," in v:
        v = v.replace(".", "").replace(",", ".")
    return round(float(v), 2) if v else 0.0


def coletar(loja: dict, pasta: Path) -> tuple[list[dict], list[str]]:
    arq = pasta / f"{loja['id']}.csv"
    if not arq.exists():
        raise FileNotFoundError(f"arquivo {arq.relative_to(pasta.parent.parent)} não encontrado")
    regs, avisos = [], []
    with open(arq, encoding="utf-8-sig", newline="") as f:
        for i, linha in enumerate(csv.DictReader(f, delimiter=";"), start=2):
            try:
                preco = _num(linha["preco"])
            except (KeyError, ValueError):
                avisos.append(f"linha {i}: preço inválido '{linha.get('preco')}'")
                continue
            if preco <= 0:
                avisos.append(f"linha {i}: preço zerado — ignorada")
                continue
            regs.append({
                "sku": linha.get("sku", "").strip() or f"linha{i}",
                "produto_id": linha.get("sku", "").strip(),
                "nome": linha.get("nome", "").strip(),
                "marca": linha.get("marca", "").strip(),
                "categoria": linha.get("categoria", "").strip() or "[sem categoria]",
                "preco": preco,
                "preco_lista": _num(linha.get("preco_lista", "")),
                "disponivel": int(str(linha.get("disponivel", "1")).strip() not in ("0", "nao", "não")),
                "url": linha.get("url", "").strip(),
                "imagem": "",
            })
    return regs, avisos
