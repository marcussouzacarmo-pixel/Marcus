# Comparativo de Preços de Móveis — Goiânia e região

Web app estático (GitHub Pages) com **ranking de custo-benefício**, filtros por **região, loja, categoria e faixa de preço**, e **comparativo de preço hoje × 30 dias × 3 meses**. Os preços são coletados automaticamente todo dia e o histórico fica gravado no próprio repositório.

## Como funciona

```
config/lojas.yml          cadastro de lojas, regiões e termos de busca por categoria
coletor/coletar.py        coleta diária -> data/historico/AAAA-MM.csv + log em data/coletas/
coletor/consolidar.py     calcula preço atual, variações, índice C/B e pendências -> docs/data/dados.json
docs/                     app (index.html, app.js, styles.css) — servido pelo GitHub Pages
.github/workflows/coleta.yml  agenda diária (05h47 de Brasília) + execução manual
```

Conectores:

| Plataforma | Como coleta | Uso |
|---|---|---|
| `vtex` | API pública de catálogo da loja (`/api/catalog_system/pub/products/search`) | e-commerces em VTEX |
| `manual` | lê `data/manual/<id>.csv` (`;` e vírgula decimal) | lojas físicas sem site |

## Ativação (uma vez)

1. **Mesclar este branch na `main`** — o agendamento do GitHub Actions só roda no branch padrão.
2. **Settings → Pages →** *Deploy from a branch* → `main` / pasta `/docs`.
3. **Actions → Coleta diária de preços → Run workflow** para a primeira coleta.
4. Abrir a aba **Pendências** do app: conferir os conectores e marcar `validado: true` em `config/lojas.yml` após checar alguns preços no site.

## Rodar localmente

```bash
pip install -r requirements.txt
python coletor/coletar.py            # ou --loja tokstok
python coletor/consolidar.py
python -m http.server -d docs 8000   # abrir http://localhost:8000
```

## Adicionar uma loja

- **E-commerce VTEX:** novo bloco em `config/lojas.yml` com `plataforma: vtex` e `base_url`.
- **Loja física:** `plataforma: manual`, criar `data/manual/<id>.csv` e manter atualizado.
- Outras plataformas (Magalu, Casas Bahia, MadeiraMadeira, Mobly, Leroy Merlin) exigem conector próprio em `coletor/plataformas/`.

## Regras de cálculo

Ver aba **Metodologia** do app. Resumo: preço de 3 meses = último preço registrado até 90 dias antes; sem registro = `[sem histórico]` (nada é estimado). Índice C/B (0–100) dentro da categoria: 50% posição de preço, 30% desconto sobre o preço "de", 20% tendência de 3 meses.
