"""Consolida o histórico de preços em docs/data/dados.json (consumido pelo app).

Regras:
  - Preço atual: última observação do produto na última coleta da sua loja.
    Produto ausente na última coleta da loja => fora do ranking (listado em Pendências).
  - Preço há N dias: última observação com data <= (data de referência - N).
    Se o produto ainda não existia no histórico nessa data => null ("sem histórico").
  - Índice custo-benefício (0-100), calculado dentro da categoria:
        50% posição de preço (percentil invertido: mais barato da categoria = 1)
        30% desconto sobre o preço de lista (teto de 50%)
        20% tendência 90 dias (queda = melhor; neutro 0,5 sem histórico)
  - Itens com preço < 20% da mediana da categoria são marcados como possível
    acessório/peça avulsa: ficam fora do índice e da mediana, e vão para Pendências.
"""
from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "docs" / "data" / "dados.json"
TZ_BR = timezone(timedelta(hours=-3))
SALTO_SUSPEITO = 0.5  # variação diária > 50% vira pendência
PISO_ACESSORIO = 0.2  # preço < 20% da mediana da categoria => possível acessório/peça avulsa


def _d(s: str) -> date:
    return date.fromisoformat(s)


def carregar_historico() -> list[dict]:
    regs = []
    for arq in sorted((RAIZ / "data" / "historico").glob("*.csv")):
        with open(arq, encoding="utf-8", newline="") as f:
            regs.extend(csv.DictReader(f))
    return regs


def preco_em(serie: list[tuple[str, float]], alvo: date) -> float | None:
    if not serie or _d(serie[0][0]) > alvo:
        return None
    val = None
    for dt, p in serie:
        if _d(dt) <= alvo:
            val = p
        else:
            break
    return val


def brl(v: float) -> str:
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def var(atual: float, antigo: float | None) -> float | None:
    return round((atual - antigo) / antigo, 4) if antigo else None


def comprimir(serie: list[tuple[str, float]]) -> list[list]:
    """Mantém só os pontos onde o preço muda (+ o último), para o gráfico."""
    out = []
    for i, (dt, p) in enumerate(serie):
        if not out or out[-1][1] != p or i == len(serie) - 1:
            out.append([dt, p])
    return out


def percentil_invertido(valores: list[float], v: float) -> float:
    if len(valores) <= 1:
        return 0.5
    abaixo = sum(1 for x in valores if x < v)
    iguais = sum(1 for x in valores if x == v)
    return 1 - (abaixo + (iguais - 1) / 2) / (len(valores) - 1)


def main() -> int:
    cfg = yaml.safe_load(open(RAIZ / "config" / "lojas.yml", encoding="utf-8"))
    lojas_cfg = {l["id"]: l for l in cfg["lojas"]}
    hist = carregar_historico()
    pendencias: list[dict] = []

    def pend(tipo, loja, detalhe, gravidade="média"):
        pendencias.append({"tipo": tipo, "loja": loja, "detalhe": detalhe, "gravidade": gravidade})

    # ---- agrupa por loja+sku ------------------------------------------------
    grupos: dict[tuple, list[dict]] = defaultdict(list)
    ult_coleta_loja: dict[str, str] = {}
    primeira_data = None
    for r in hist:
        grupos[(r["loja_id"], r["sku"])].append(r)
        ult_coleta_loja[r["loja_id"]] = max(ult_coleta_loja.get(r["loja_id"], ""), r["data"])
        primeira_data = min(primeira_data or r["data"], r["data"])

    data_ref = max(ult_coleta_loja.values()) if ult_coleta_loja else None
    ref = _d(data_ref) if data_ref else None

    produtos = []
    fora_linha = defaultdict(int)
    for (loja_id, sku), obs in grupos.items():
        obs.sort(key=lambda r: r["data"])
        por_dia = {o["data"]: o for o in obs}  # 1 observação por dia (a última gravada)
        if len(por_dia) < len(obs):
            pend("SKU duplicado no mesmo dia", loja_id,
                 f"SKU {sku}: {len(obs) - len(por_dia)} registro(s) repetido(s) — mantido o último de cada dia.", "baixa")
        obs = list(por_dia.values())
        ult = obs[-1]
        if loja_id not in lojas_cfg:
            continue
        if ult["data"] != ult_coleta_loja[loja_id]:
            fora_linha[loja_id] += 1
            continue
        serie = [(o["data"], float(o["preco"])) for o in obs]
        preco = float(ult["preco"])
        lista = float(ult["preco_lista"] or 0)

        # qualidade de dados
        for (d0, p0), (d1, p1) in zip(serie, serie[1:]):
            if p0 and abs(p1 - p0) / p0 > SALTO_SUSPEITO:
                pend("Salto de preço suspeito", loja_id,
                     f"{ult['nome'][:70]} (SKU {sku}): {brl(p0)} em {d0} → {brl(p1)} em {d1}")
        if lista and lista < preco:
            pend("Preço de lista menor que preço de venda", loja_id,
                 f"{ult['nome'][:70]} (SKU {sku}): lista {brl(lista)} < venda {brl(preco)}", "baixa")

        p30 = preco_em(serie, ref - timedelta(days=30))
        p90 = preco_em(serie, ref - timedelta(days=90))
        loja = lojas_cfg[loja_id]
        produtos.append({
            "loja_id": loja_id, "loja": loja["nome"], "regiao": loja.get("regiao", ""),
            "sku": sku, "nome": ult["nome"], "marca": ult.get("marca", ""),
            "categoria": ult["categoria"], "url": ult.get("url", ""), "imagem": ult.get("imagem", ""),
            "disponivel": ult.get("disponivel") == "1",
            "preco": preco, "preco_lista": lista or None,
            "desconto": round((lista - preco) / lista, 4) if lista > preco else 0.0,
            "preco_30d": p30, "var_30d": var(preco, p30),
            "preco_90d": p90, "var_90d": var(preco, p90),
            "primeira_obs": serie[0][0],
            "serie": comprimir(serie),
        })

    # ---- índice custo-benefício por categoria -------------------------------
    por_cat = defaultdict(list)
    for p in produtos:
        por_cat[p["categoria"]].append(p)
    resumo_cat = {}
    suspeitos = defaultdict(list)
    for cat, itens in por_cat.items():
        med_bruta = statistics.median(p["preco"] for p in itens)
        for p in itens:
            p["suspeito"] = p["preco"] < PISO_ACESSORIO * med_bruta
            if p["suspeito"]:
                suspeitos[(p["loja_id"], cat)].append(p)
                p["score"] = None
                p["vs_mediana"] = round((p["preco"] - med_bruta) / med_bruta, 4)
        validos = [p for p in itens if not p["suspeito"]]
        precos = [p["preco"] for p in validos] or [p["preco"] for p in itens]
        med = statistics.median(precos)
        resumo_cat[cat] = {"itens": len(validos), "suspeitos": len(itens) - len(validos),
                           "mediana": med, "min": min(precos), "max": max(precos)}
        for p in validos:
            s_preco = percentil_invertido(precos, p["preco"])
            s_desc = min(p["desconto"] / 0.5, 1.0)
            v = p["var_90d"]
            s_tend = 0.5 if v is None else max(0.0, min(1.0, 0.5 - v / 0.6))
            p["score"] = round(100 * (0.5 * s_preco + 0.3 * s_desc + 0.2 * s_tend), 1)
            p["vs_mediana"] = round((p["preco"] - med) / med, 4) if med else None

    for (lid, cat), itens in sorted(suspeitos.items()):
        ex = "; ".join(f"{p['nome'][:40]} ({brl(p['preco'])})" for p in sorted(itens, key=lambda x: x["preco"])[:3])
        pend("Possível acessório/peça na categoria", lid,
             f"{cat}: {len(itens)} item(ns) abaixo de 20% da mediana — fora do índice C/B. Ex.: {ex}", "baixa")

    # ---- resumo por loja + pendências de cadastro/coleta --------------------
    log = None
    logs = sorted((RAIZ / "data" / "coletas").glob("*.json"))
    if logs:
        log = json.loads(logs[-1].read_text(encoding="utf-8"))
        for e in log["lojas"]:
            if e["status"] == "erro":
                pend("Falha na coleta", e["loja_id"], f"{log['data']}: {e.get('erro')}", "alta")
            elif e["status"] == "vazio":
                pend("Coleta sem itens", e["loja_id"], f"{log['data']}: nenhum produto retornado", "alta")
            for a in e.get("avisos", [])[:5]:
                pend("Aviso de coleta", e["loja_id"], a, "baixa")

    lojas_out = []
    for lid, l in lojas_cfg.items():
        itens = [p for p in produtos if p["loja_id"] == lid]
        v90 = [p["var_90d"] for p in itens if p["var_90d"] is not None]
        lojas_out.append({
            "id": lid, "nome": l["nome"], "regiao": l.get("regiao", ""), "cidade": l.get("cidade", ""),
            "plataforma": l["plataforma"], "ativo": bool(l.get("ativo")), "validado": bool(l.get("validado")),
            "observacao": l.get("observacao", ""), "ultima_coleta": ult_coleta_loja.get(lid),
            "itens": len(itens), "fora_linha": fora_linha.get(lid, 0),
            "var_90d_media": round(statistics.mean(v90), 4) if v90 else None,
            "itens_com_hist_90d": len(v90),
        })
        if l.get("ativo") and not l.get("validado"):
            pend("Conector não validado", lid,
                 "Confirmar se os preços conferem com o site antes de usar a loja em decisões; depois marcar validado: true.")
        if fora_linha.get(lid):
            pend("Produtos fora da última coleta", lid,
                 f"{fora_linha[lid]} SKU(s) coletados antes e ausentes na última coleta (esgotados/retirados) — fora do ranking.",
                 "baixa")

    if ref and primeira_data and (ref - _d(primeira_data)).days < 90:
        pend("Histórico insuficiente para 90 dias", "—",
             f"Coleta iniciada em {primeira_data}; variação de 3 meses disponível a partir de "
             f"{(_d(primeira_data) + timedelta(days=90)).isoformat()}.", "média")

    ordem = {"alta": 0, "média": 1, "baixa": 2}
    pendencias.sort(key=lambda x: (ordem[x["gravidade"]], x["loja"], x["tipo"]))

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps({
        "gerado_em": datetime.now(TZ_BR).isoformat(timespec="seconds"),
        "data_referencia": data_ref,
        "inicio_historico": primeira_data,
        "lojas": lojas_out,
        "categorias": resumo_cat,
        "produtos": sorted(produtos, key=lambda p: -(p["score"] if p["score"] is not None else -1)),
        "pendencias": pendencias,
        "metodologia": __doc__.strip(),
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"dados.json: {len(produtos)} produtos, {len(lojas_out)} lojas, {len(pendencias)} pendências")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
