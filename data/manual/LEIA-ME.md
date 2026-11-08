# Lojas manuais (sem e-commerce)

1. Copie `exemplo_local.csv` para `<id_da_loja>.csv` (ex.: `moveis_centro.csv`).
2. Preencha uma linha por produto. Separador `;`, decimal com vírgula.
   - `sku`: código da etiqueta/orçamento (ou um código seu, fixo para o mesmo produto)
   - `categoria`: use exatamente uma destas — Sofás, Camas e Box, Colchões, Guarda-roupas,
     Mesas de jantar, Cadeiras, Racks e Painéis, Cozinhas, Escrivaninhas
   - `preco`: preço à vista; `preco_lista`: preço "de" (opcional); `disponivel`: 1 ou 0
3. Cadastre a loja em `config/lojas.yml` com `plataforma: manual`, `regiao`, `cidade` e `ativo: true`.
4. A cada nova pesquisa de preço, atualize o CSV. A coleta diária registra o preço do CSV
   com a data do dia — **mantenha o mesmo `sku` para o mesmo produto**, senão o histórico se perde.
