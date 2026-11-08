/* Comparativo de Preços de Móveis — front-end estático (lê data/dados.json) */
(() => {
  const POR_PAGINA = 50;
  const $ = (s) => document.querySelector(s);
  const brl = (v) => v == null ? null : v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  const pct = (v) => v == null ? null : (v > 0 ? "+" : "") + (v * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + "%";
  const dataBR = (s) => s ? s.split("-").reverse().join("/") : "—";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const semHist = '<span class="pend-txt">[sem histórico]</span>';
  const clsVar = (v) => v == null ? "" : v < 0 ? "pos" : v > 0 ? "neg" : "";
  const corScore = (s) => s >= 70 ? "#1E7B4A" : s >= 50 ? "#2E5FA3" : s >= 35 ? "#B26A00" : "#8A8F99";
  const mediana = (a) => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y); const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };

  let D = null, pagina = 1, lojasSel = new Set(), graficos = {};
  const PREF = "comparativo-moveis-filtros";

  // ---------- abas ----------
  document.querySelectorAll(".aba").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".aba").forEach((x) => x.classList.toggle("ativa", x === b));
    document.querySelectorAll(".painel").forEach((p) => p.classList.toggle("ativo", p.id === "aba-" + b.dataset.aba));
  }));

  // ---------- carga ----------
  fetch("data/dados.json", { cache: "no-store" })
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((d) => { D = d; iniciar(); })
    .catch(() => {
      $("#status-dados").textContent = "Sem dados publicados ainda — aguardando a primeira coleta automática.";
      $("#tabela tbody").innerHTML = '<tr><td colspan="11" class="vazio">Nenhum dado disponível.</td></tr>';
    });

  function iniciar() {
    $("#status-dados").textContent =
      `Preços de ${dataBR(D.data_referencia)} · histórico desde ${dataBR(D.inicio_historico)} · ` +
      `${D.produtos.length.toLocaleString("pt-BR")} produtos em ${D.lojas.filter((l) => l.itens).length} lojas`;
    $("#qtd-pend").textContent = D.pendencias.filter((p) => p.gravidade !== "baixa").length || "";

    const regioes = [...new Set(D.lojas.filter((l) => l.ativo).map((l) => l.regiao))].sort();
    regioes.forEach((r) => $("#f-regiao").append(new Option(r, r)));
    Object.keys(D.categorias).sort().forEach((c) => $("#f-categoria").append(new Option(c, c)));

    restaurarFiltros();
    montarChips();
    ["#f-regiao", "#f-categoria", "#f-ordem", "#f-disp"].forEach((s) => $(s).addEventListener("change", () => {
      if (s === "#f-regiao") { lojasSel.clear(); montarChips(); }
      pagina = 1; render();
    }));
    ["#f-min", "#f-max", "#f-busca"].forEach((s) => $(s).addEventListener("input", () => { pagina = 1; render(); }));

    render();
    renderLojas();
    renderVariacao();
    renderPendencias();
  }

  // ---------- filtros ----------
  function lojasDaRegiao() {
    const reg = $("#f-regiao").value;
    return D.lojas.filter((l) => l.ativo && (!reg || l.regiao === reg));
  }

  function montarChips() {
    const box = $("#f-lojas");
    box.innerHTML = "";
    const todas = document.createElement("button");
    todas.className = "chip" + (lojasSel.size ? "" : " on");
    todas.textContent = "Todas as lojas";
    todas.onclick = () => { lojasSel.clear(); montarChips(); pagina = 1; render(); };
    box.append(todas);
    lojasDaRegiao().forEach((l) => {
      const b = document.createElement("button");
      b.className = "chip" + (lojasSel.has(l.id) ? " on" : "");
      b.innerHTML = `${esc(l.nome)} <small>${l.itens}</small>`;
      b.title = `${l.cidade} · ${l.regiao}`;
      b.onclick = () => { lojasSel.has(l.id) ? lojasSel.delete(l.id) : lojasSel.add(l.id); montarChips(); pagina = 1; render(); };
      box.append(b);
    });
  }

  function filtrados() {
    const reg = $("#f-regiao").value, cat = $("#f-categoria").value;
    const min = parseFloat($("#f-min").value), max = parseFloat($("#f-max").value);
    const termos = $("#f-busca").value.trim().toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").split(/\s+/).filter(Boolean);
    const disp = $("#f-disp").checked;
    const ok = new Set(lojasDaRegiao().map((l) => l.id));
    let L = D.produtos.filter((p) =>
      ok.has(p.loja_id) && (!lojasSel.size || lojasSel.has(p.loja_id)) && (!reg || p.regiao === reg) &&
      (!cat || p.categoria === cat) && (isNaN(min) || p.preco >= min) && (isNaN(max) || p.preco <= max) &&
      (!disp || p.disponivel) &&
      (!termos.length || termos.every((t) => (p.nome + " " + p.marca).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").includes(t))));
    const ord = $("#f-ordem").value;
    const nulo = (v, dflt) => v == null ? dflt : v;
    const cmp = {
      score: (a, b) => b.score - a.score,
      preco_asc: (a, b) => a.preco - b.preco,
      preco_desc: (a, b) => b.preco - a.preco,
      queda: (a, b) => nulo(a.var_90d, Infinity) - nulo(b.var_90d, Infinity),
      alta: (a, b) => nulo(b.var_90d, -Infinity) - nulo(a.var_90d, -Infinity),
      desconto: (a, b) => b.desconto - a.desconto,
    }[ord];
    salvarFiltros();
    return L.sort(cmp);
  }

  function salvarFiltros() {
    try {
      localStorage.setItem(PREF, JSON.stringify({
        regiao: $("#f-regiao").value, categoria: $("#f-categoria").value, ordem: $("#f-ordem").value,
        disp: $("#f-disp").checked, lojas: [...lojasSel],
      }));
    } catch (_) { /* sem armazenamento: ignora */ }
  }
  function restaurarFiltros() {
    try {
      const f = JSON.parse(localStorage.getItem(PREF) || "null");
      if (!f) return;
      const set = (s, v) => { if ([...$(s).options].some((o) => o.value === v)) $(s).value = v; };
      set("#f-regiao", f.regiao); set("#f-categoria", f.categoria); set("#f-ordem", f.ordem);
      $("#f-disp").checked = f.disp !== false;
      (f.lojas || []).forEach((id) => D.lojas.some((l) => l.id === id) && lojasSel.add(id));
    } catch (_) { /* ignora */ }
  }

  // ---------- ranking ----------
  function render() {
    const L = filtrados();
    const precos = L.map((p) => p.preco);
    const v90 = L.map((p) => p.var_90d).filter((v) => v != null);
    $("#kpis").innerHTML = [
      ["Produtos no filtro", L.length.toLocaleString("pt-BR")],
      ["Preço mediano", brl(mediana(precos)) ?? "—"],
      ["Menor preço", brl(precos.length ? Math.min(...precos) : null) ?? "—"],
      ["Variação mediana 3m", v90.length ? pct(mediana(v90)) : "[sem histórico]"],
      ["Com histórico de 3m", L.length ? Math.round(100 * v90.length / L.length) + "%" : "—"],
    ].map(([t, v]) => `<div class="kpi"><b>${v}</b><span>${t}</span></div>`).join("");

    const ini = (pagina - 1) * POR_PAGINA;
    const tb = $("#tabela tbody");
    tb.innerHTML = L.length ? L.slice(ini, ini + POR_PAGINA).map((p, i) => `
      <tr data-k="${esc(p.loja_id)}|${esc(p.sku)}">
        <td>${ini + i + 1}</td>
        <td><div class="prod">${p.imagem ? `<img loading="lazy" src="${esc(p.imagem)}" alt="">` : ""}
          <div>${esc(p.nome)}<small>${esc(p.marca)}${p.disponivel ? "" : " · indisponível"}</small></div></div></td>
        <td>${esc(p.loja)}<br><small class="pend-txt" style="font-style:normal">${esc(p.regiao)}</small></td>
        <td>${esc(p.categoria)}</td>
        <td class="num"><b>${brl(p.preco)}</b>${p.preco_lista && p.preco_lista > p.preco ? `<br><small><s>${brl(p.preco_lista)}</s></small>` : ""}</td>
        <td class="num">${brl(p.preco_90d) ?? semHist}</td>
        <td class="num ${clsVar(p.var_90d)}">${pct(p.var_90d) ?? semHist}</td>
        <td class="num ${clsVar(p.var_30d)}">${pct(p.var_30d) ?? semHist}</td>
        <td class="num">${p.desconto ? pct(-p.desconto) : "—"}</td>
        <td class="num ${clsVar(p.vs_mediana)}">${pct(p.vs_mediana) ?? "—"}</td>
        <td class="num"><span class="score" style="background:${corScore(p.score)}">${p.score.toLocaleString("pt-BR")}</span></td>
      </tr>`).join("") : '<tr><td colspan="11" class="vazio">Nenhum produto com esses filtros.</td></tr>';
    tb.querySelectorAll("tr[data-k]").forEach((tr) => tr.onclick = () => abrirProduto(tr.dataset.k));

    const n = Math.ceil(L.length / POR_PAGINA), pg = $("#paginacao");
    pg.innerHTML = "";
    if (n > 1) for (let i = 1; i <= n; i++) {
      if (n > 12 && i > 2 && i < n - 1 && Math.abs(i - pagina) > 2) { if (!pg.lastChild?.disabled) { const s = document.createElement("button"); s.textContent = "…"; s.disabled = true; pg.append(s); } continue; }
      const b = document.createElement("button");
      b.textContent = i; b.className = i === pagina ? "on" : "";
      b.onclick = () => { pagina = i; render(); window.scrollTo({ top: 0, behavior: "smooth" }); };
      pg.append(b);
    }
  }

  function abrirProduto(k) {
    const [lid, sku] = k.split("|");
    const p = D.produtos.find((x) => x.loja_id === lid && x.sku === sku);
    if (!p) return;
    $("#m-nome").textContent = p.nome;
    $("#m-info").textContent = `${p.loja} · ${p.categoria} · hoje ${brl(p.preco)} · há 3 meses ${brl(p.preco_90d) ?? "[sem histórico]"} · ` +
      `1ª observação ${dataBR(p.primeira_obs)} · índice C/B ${p.score}`;
    const a = $("#m-link");
    a.href = p.url || "#"; a.style.display = p.url ? "" : "none";
    graficos.produto?.destroy();
    if (window.Chart) graficos.produto = new Chart($("#g-produto"), {
      type: "line",
      data: { labels: p.serie.map((s) => dataBR(s[0])), datasets: [{ label: "Preço (R$)", data: p.serie.map((s) => s[1]), stepped: true, borderColor: "#2E5FA3", backgroundColor: "rgba(46,95,163,.12)", fill: true, pointRadius: 3 }] },
      options: { plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => brl(c.parsed.y) } } }, scales: { y: { ticks: { callback: (v) => brl(v) } } } },
    });
    $("#modal").showModal();
  }

  // ---------- lojas ----------
  function renderLojas() {
    $("#cards-lojas").innerHTML = D.lojas.map((l) => `
      <div class="card">
        <h3>${esc(l.nome)}</h3>
        <div>${l.ativo ? '<span class="tag">ativa</span>' : '<span class="tag alerta">inativa</span>'}
          ${l.validado ? '<span class="tag">conector validado</span>' : '<span class="tag alerta">conector não validado</span>'}
          <span class="tag">${esc(l.plataforma)}</span></div>
        <dl>
          <dt>Região</dt><dd>${esc(l.regiao)}</dd>
          <dt>Cidade</dt><dd>${esc(l.cidade)}</dd>
          <dt>Última coleta</dt><dd>${dataBR(l.ultima_coleta)}</dd>
          <dt>Produtos no ranking</dt><dd>${l.itens.toLocaleString("pt-BR")}</dd>
          <dt>Fora da última coleta</dt><dd>${l.fora_linha}</dd>
          <dt>Var. média 3m</dt><dd class="${clsVar(l.var_90d_media)}">${pct(l.var_90d_media) ?? "[sem histórico]"}</dd>
        </dl>
        ${l.observacao ? `<p class="pend-txt" style="font-size:12px">${esc(l.observacao)}</p>` : ""}
      </div>`).join("");
  }

  // ---------- variação ----------
  function renderVariacao() {
    const comHist = D.produtos.filter((p) => p.var_90d != null);
    if (!comHist.length) {
      $("#nota-variacao").textContent = `Ainda não há produtos com 90 dias de histórico (coleta iniciada em ${dataBR(D.inicio_historico)}). ` +
        "Os gráficos serão preenchidos automaticamente conforme o histórico se acumula.";
    }
    const agrupa = (campo) => {
      const g = {};
      comHist.forEach((p) => (g[p[campo]] ??= []).push(p.var_90d));
      return Object.entries(g).map(([k, v]) => [k, mediana(v)]).sort((a, b) => a[1] - b[1]);
    };
    const barra = (id, pares) => {
      if (!window.Chart) return;
      graficos[id]?.destroy();
      graficos[id] = new Chart($(id), {
        type: "bar",
        data: { labels: pares.map((x) => x[0]), datasets: [{ data: pares.map((x) => +(x[1] * 100).toFixed(2)), backgroundColor: pares.map((x) => x[1] < 0 ? "#1E7B4A" : "#B3261E") }] },
        options: { indexAxis: "y", plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => c.parsed.x.toLocaleString("pt-BR") + "%" } } }, scales: { x: { ticks: { callback: (v) => v + "%" } } } },
      });
    };
    barra("#g-cat", agrupa("categoria"));
    barra("#g-loja", agrupa("loja"));

    const linha = (p) => `<tr><td>${esc(p.nome).slice(0, 70)}<br><small class="pend-txt" style="font-style:normal">${esc(p.loja)}</small></td>
      <td class="num">${brl(p.preco_90d)} → ${brl(p.preco)}</td><td class="num ${clsVar(p.var_90d)}">${pct(p.var_90d)}</td></tr>`;
    const ord = [...comHist].sort((a, b) => a.var_90d - b.var_90d);
    const vazio = '<tr><td class="vazio">[sem histórico de 3 meses]</td></tr>';
    $("#t-quedas tbody").innerHTML = ord.filter((p) => p.var_90d < 0).slice(0, 10).map(linha).join("") || vazio;
    $("#t-altas tbody").innerHTML = ord.reverse().filter((p) => p.var_90d > 0).slice(0, 10).map(linha).join("") || vazio;
  }

  // ---------- pendências ----------
  function renderPendencias() {
    $("#t-pend tbody").innerHTML = D.pendencias.length ? D.pendencias.map((p) => `
      <tr><td class="grav-${esc(p.gravidade)}">${esc(p.gravidade)}</td><td>${esc(p.tipo)}</td><td>${esc(p.loja)}</td><td>${esc(p.detalhe)}</td></tr>`).join("")
      : '<tr><td colspan="4" class="vazio">Nenhuma pendência.</td></tr>';
  }
})();
