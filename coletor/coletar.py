"""Coleta diária de preços das lojas cadastradas em config/lojas.yml.

Saídas:
  data/historico/AAAA-MM.csv  -> uma linha por produto/loja/dia (append, idempotente por dia)
  data/coletas/AAAA-MM-DD.json -> log da execução (sucessos, falhas, contagens)

Uso:
  python coletor/coletar.py               # coleta todas as lojas ativas
  python coletor/coletar.py --loja tokstok
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from coletor.plataformas import vtex, manual, wake  # noqa: E402

TZ_BR = timezone(timedelta(hours=-3))  # America/Sao_Paulo (sem horário de verão desde 2019)
CAMPOS = [
    "data", "loja_id", "sku", "produto_id", "nome", "marca", "categoria",
    "preco", "preco_lista", "disponivel", "url", "imagem",
]


def carregar_config() -> dict:
    with open(RAIZ / "config" / "lojas.yml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def gravar_historico(registros: list[dict], hoje: str) -> int:
    """Grava no CSV do mês, substituindo registros do mesmo dia/loja (reexecução segura)."""
    pasta = RAIZ / "data" / "historico"
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / f"{hoje[:7]}.csv"
    lojas_hoje = {r["loja_id"] for r in registros}

    existentes: list[dict] = []
    if arq.exists():
        with open(arq, encoding="utf-8", newline="") as f:
            existentes = [
                r for r in csv.DictReader(f)
                if not (r["data"] == hoje and r["loja_id"] in lojas_hoje)
            ]

    with open(arq, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        w.writeheader()
        w.writerows(existentes)
        w.writerows({k: r.get(k, "") for k in CAMPOS} for r in registros)
    return len(registros)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--loja", help="coletar apenas esta loja (id)")
    args = ap.parse_args()

    cfg = carregar_config()
    hoje = datetime.now(TZ_BR).strftime("%Y-%m-%d")
    params = cfg.get("coleta", {})
    log = {"data": hoje, "inicio": datetime.now(TZ_BR).isoformat(), "lojas": []}
    todos: list[dict] = []

    for loja in cfg["lojas"]:
        if args.loja and loja["id"] != args.loja:
            continue
        if not loja.get("ativo"):
            continue
        t0 = time.time()
        entrada = {"loja_id": loja["id"], "plataforma": loja["plataforma"]}
        try:
            if loja["plataforma"] == "vtex":
                regs, avisos = vtex.coletar(loja, cfg["categorias"], params)
            elif loja["plataforma"] == "wake":
                regs, avisos = wake.coletar(loja, cfg["categorias"], params)
            elif loja["plataforma"] == "manual":
                regs, avisos = manual.coletar(loja, RAIZ / "data" / "manual")
            else:
                raise ValueError(f"plataforma desconhecida: {loja['plataforma']}")
            for r in regs:
                r["data"] = hoje
                r["loja_id"] = loja["id"]
            todos.extend(regs)
            entrada.update(status="ok" if regs else "vazio", itens=len(regs), avisos=avisos)
        except Exception as e:  # falha de uma loja não derruba a coleta das demais
            entrada.update(status="erro", itens=0, erro=f"{type(e).__name__}: {e}")
        entrada["segundos"] = round(time.time() - t0, 1)
        log["lojas"].append(entrada)
        print(f"[{entrada['status']:>5}] {loja['id']}: {entrada['itens']} itens"
              + (f" — {entrada.get('erro')}" if entrada.get("erro") else ""))

    if todos:
        gravar_historico(todos, hoje)

    log["fim"] = datetime.now(TZ_BR).isoformat()
    pasta_log = RAIZ / "data" / "coletas"
    pasta_log.mkdir(parents=True, exist_ok=True)
    (pasta_log / f"{hoje}.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
