// Árvore interativa: a raiz fica embaixo (no tronco) e cada geração é um andar acima.
// Clique numa pessoa para ver os detalhes e abrir/fechar os filhos dela.
// Arraste para mover, use a roda do mouse (ou os botões) para aproximar.
(function () {
  "use strict";
  const DADOS = window.ARVORES || [];
  const RAIZ = window.RAIZ || "";
  const palco = document.getElementById("palco");
  if (!palco || !DADOS.length) return;

  const NS = "http://www.w3.org/2000/svg";
  const CORES = [["#F5C6C6", "#D98E8E"], ["#F9D8AE", "#D9A866"], ["#F4E8A6", "#C9B655"], ["#CDE8C4", "#86B57A"],
                 ["#C3E1EF", "#73AECB"], ["#D7CDEF", "#9887CF"], ["#F1CBE3", "#C985B2"]];
  const PARENTESCO = ["fundador(a) do ramo", "filho(a)", "neto(a)", "bisneto(a)", "trineto(a)", "tetraneto(a)", "pentaneto(a)", "hexaneto(a)"];
  const LARG = 140, ALT = 50, PASSO_X = 154, PASSO_Y = 120, DUR = 480;
  const cor = (g) => CORES[(g - 1) % CORES.length];
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const el = (tag, attrs = {}, pai) => {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (pai) pai.appendChild(e);
    return e;
  };
  const corta = (t, n) => (t.length > n ? t.slice(0, n - 1) + "…" : t);

  // ---------------------------------------------------------------- estrutura
  const svg = el("svg", { class: "arvore-svg", role: "img", "aria-label": "Árvore genealógica interativa" }, palco);
  const defs = el("defs", {}, svg);
  defs.innerHTML = `
    <linearGradient id="ceu" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#EAF3FA"/><stop offset="1" stop-color="#FDF8EE"/></linearGradient>
    <filter id="sombra" x="-20%" y="-20%" width="140%" height="160%"><feDropShadow dx="0" dy="2" stdDeviation="2.5" flood-color="#7a5c3c" flood-opacity=".18"/></filter>`;
  el("rect", { x: 0, y: 0, width: "100%", height: "100%", fill: "url(#ceu)" }, svg);
  const camada = el("g", {}, svg);
  const gChao = el("g", { class: "chao" }, camada);
  const gLinks = el("g", { class: "links" }, camada);
  const gNos = el("g", { class: "nos" }, camada);

  const painel = document.getElementById("painel");
  const abas = document.getElementById("abas");
  const legenda = document.getElementById("legenda-geracoes");

  let familia = null, raiz = null, selecionado = null;
  let vista = { x: 0, y: 0, k: 1 };
  const porId = new Map();

  function preparar(no, pai) {
    no.pai = pai;
    no.aberto = false;
    no.x = no.x0 = 0; no.y = no.y0 = 0;
    porId.set(no.id, no);
    (no.k || []).forEach((f) => preparar(f, no));
    no.desc = (no.k || []).reduce((s, f) => s + 1 + f.desc, 0);
  }

  // ------------------------------------------------------------------ layout
  function visiveis(no, out = []) {
    out.push(no);
    if (no.aberto) (no.k || []).forEach((f) => visiveis(f, out));
    return out;
  }
  function layout() {
    let proxima = 0;
    (function posicionar(no) {
      const filhos = no.aberto ? no.k || [] : [];
      if (!filhos.length) { no.tx = proxima++ * PASSO_X; }
      else { filhos.forEach(posicionar); no.tx = (filhos[0].tx + filhos[filhos.length - 1].tx) / 2; }
      no.ty = -(no.g - 1) * PASSO_Y;
    })(raiz);
  }

  // ----------------------------------------------------------------- desenho
  const caminho = (a, b) => {
    const y1 = a.y - ALT / 2, y2 = b.y + ALT / 2, m = (y1 + y2) / 2;
    return `M${a.x},${y1} C${a.x},${m} ${b.x},${m} ${b.x},${y2}`;
  };
  const elementos = new Map(); // id -> {g, link}

  function criarNo(no) {
    const [preench, contorno] = cor(no.g);
    const g = el("g", { class: "no", tabindex: 0, role: "button", "aria-label": no.n }, gNos);
    el("rect", { x: -LARG / 2, y: -ALT / 2, width: LARG, height: ALT, rx: 14, fill: preench, stroke: contorno, "stroke-width": 1.6, filter: "url(#sombra)" }, g);
    const t1 = el("text", { class: "nome", x: 0, y: no.c || no.ano ? -5 : 5, "text-anchor": "middle" }, g);
    t1.textContent = corta(no.n, 19);
    if (no.c || no.ano) {
      const t2 = el("text", { class: "sub", x: 0, y: 13, "text-anchor": "middle" }, g);
      t2.textContent = corta([[no.ano, no.f ? "†" : ""].filter(Boolean).join(" "), no.c ? "⚭ " + no.c : ""].filter(Boolean).join("  "), 26);
    }
    const tit = el("title", {}, g);
    tit.textContent = `${no.n}${no.ano ? " (" + no.ano + ")" : ""}${no.c ? " ⚭ " + no.c : ""}`;
    if ((no.k || []).length) {
      const b = el("g", { class: "botao" }, g);
      el("circle", { cx: 0, cy: -ALT / 2 - 2, r: 11, fill: "#fff", stroke: contorno, "stroke-width": 1.6 }, b);
      el("text", { class: "mais", x: 0, y: -ALT / 2 + 2, "text-anchor": "middle" }, b);
    }
    g.addEventListener("click", (e) => { e.stopPropagation(); clicar(no); });
    g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); clicar(no); } });
    let link = null;
    if (no.pai) {
      link = el("path", { class: "galho", fill: "none", stroke: no.g <= 3 ? "#B8916C" : "#C9AA8A", "stroke-width": Math.max(2, 9 - no.g * 1.3), "stroke-linecap": "round" }, gLinks);
    }
    const reg = { g, link };
    elementos.set(no.id, reg);
    return reg;
  }

  function atualizarBotao(no) {
    const reg = elementos.get(no.id);
    const t = reg && reg.g.querySelector(".mais");
    if (t) t.textContent = no.aberto ? "−" : "+" + no.k.length;
    reg && reg.g.classList.toggle("selecionado", no === selecionado);
  }

  let animacao = null;
  function desenhar(focar) {
    layout();
    const vis = visiveis(raiz);
    const ids = new Set(vis.map((n) => n.id));
    // nós que saem: encolhem para dentro do ancestral visível
    for (const [id, reg] of elementos) {
      if (!ids.has(id)) {
        const no = porId.get(id);
        let anc = no.pai; while (anc && !ids.has(anc.id)) anc = anc.pai;
        no.saindo = anc;
      }
    }
    vis.forEach((no) => {
      if (!elementos.has(no.id)) {
        const origem = no.pai || no;
        no.x = no.x0 = origem.x; no.y = no.y0 = origem.y;
        criarNo(no).g.style.opacity = 0;
      }
      no.x0 = no.x; no.y0 = no.y;
      atualizarBotao(no);
    });
    desenharChao(vis);
    cancelAnimationFrame(animacao);
    const t0 = performance.now();
    const passo = (agora) => {
      const t = Math.min(1, (agora - t0) / DUR), e = t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      for (const [id, reg] of elementos) {
        const no = porId.get(id);
        let x, y, op = 1;
        if (no.saindo) { x = no.x0 + (no.saindo.tx - no.x0) * e; y = no.y0 + (no.saindo.ty - no.y0) * e; op = 1 - e; }
        else { x = no.x0 + (no.tx - no.x0) * e; y = no.y0 + (no.ty - no.y0) * e; if (reg.g.style.opacity !== "1") op = e; }
        no.x = x; no.y = y;
        reg.g.setAttribute("transform", `translate(${x},${y})`);
        reg.g.style.opacity = op;
        if (reg.link) { reg.link.setAttribute("d", caminho(no.pai, no)); reg.link.style.opacity = op; }
      }
      if (t < 1) animacao = requestAnimationFrame(passo);
      else {
        for (const [id, reg] of [...elementos]) {
          const no = porId.get(id);
          if (no.saindo) { reg.g.remove(); reg.link && reg.link.remove(); elementos.delete(id); no.saindo = null; }
          else reg.g.style.opacity = 1;
        }
      }
    };
    animacao = requestAnimationFrame(passo);
    if (focar) centralizar(focar, true);
  }

  function desenharChao(vis) {
    const xs = vis.map((n) => n.tx);
    const min = Math.min(...xs), max = Math.max(...xs);
    gChao.innerHTML = "";
    el("ellipse", { cx: (min + max) / 2, cy: 150, rx: Math.max(420, (max - min) / 2 + 380), ry: 70, fill: "#DDEDD0" }, gChao);
    el("ellipse", { cx: raiz.tx, cy: 140, rx: 240, ry: 34, fill: "#CFE5BF" }, gChao);
    el("path", { d: `M${raiz.tx - 18},${ALT / 2} L${raiz.tx + 18},${ALT / 2} L${raiz.tx + 34},120 L${raiz.tx - 34},120 Z`, fill: "#C9A27C" }, gChao);
    for (const s of [-1, 1]) {
      el("path", { d: `M${raiz.tx + s * 14},112 Q${raiz.tx + s * 40},120 ${raiz.tx + s * 66},134`, stroke: "#C9A27C", "stroke-width": 9, fill: "none", "stroke-linecap": "round" }, gChao);
    }
  }

  // --------------------------------------------------------------- interação
  function clicar(no) {
    selecionado = no;
    if ((no.k || []).length) no.aberto = !no.aberto;
    mostrarPainel(no);
    elementos.forEach((_, id) => atualizarBotao(porId.get(id)));
    desenhar(no);
    history.replaceState(null, "", `#${familia.pasta}/${no.id}`);
  }

  function abrirAte(no) {
    for (let a = no.pai; a; a = a.pai) a.aberto = true;
  }

  function mostrarPainel(no) {
    const [preench, contorno] = cor(no.g);
    const caminhoAnc = [];
    for (let a = no.pai; a; a = a.pai) caminhoAnc.unshift(a);
    const filhos = (no.k || []).length;
    const conj = no.cl
      ? `<a href="#${esc(no.cl.f)}/${esc(no.cl.id)}" data-pular="${esc(no.cl.f)}/${esc(no.cl.id)}">${esc(no.c)}</a> <span class="mini">(árvore ${esc(no.cl.s)})</span>`
      : esc(no.c);
    painel.innerHTML = `
      <div class="painel-topo" style="--p:${preench};--c:${contorno}">
        ${no.foto ? `<img src="${RAIZ}${encodeURI(no.foto)}" alt="">` : `<div class="avatar">${esc(no.n[0] || "?")}</div>`}
        <div><h3>${esc(no.n)}</h3><p class="mini">${no.g}ª geração · ${PARENTESCO[Math.min(no.g - 1, PARENTESCO.length - 1)]}${no.g > 1 ? " de " + esc(raiz.n) : ""}</p></div>
      </div>
      <dl>
        ${no.ano ? `<dt>Nascimento</dt><dd>${esc(no.ano)}</dd>` : ""}
        ${no.f ? `<dt>Falecimento</dt><dd>in memoriam</dd>` : ""}
        ${no.c ? `<dt>${no.c.includes(",") ? "Uniões" : "Cônjuge"}</dt><dd>${conj}</dd>` : ""}
        ${no.pai && no.o ? `<dt>Pais</dt><dd>${esc(no.pai.n)} e ${esc(no.o)}</dd>` : ""}
        <dt>Filhos</dt><dd>${filhos || "nenhum cadastrado"}</dd>
        ${no.desc > filhos ? `<dt>Descendentes</dt><dd>${no.desc}</dd>` : ""}
      </dl>
      ${caminhoAnc.length ? `<p class="mini">Linha: ${caminhoAnc.map((a) => `<a href="#${familia.pasta}/${a.id}" data-pular="${familia.pasta}/${a.id}">${esc(a.n)}</a>`).join(" › ")} › <strong>${esc(no.n)}</strong></p>` : ""}
      <div class="acoes">
        <a class="botao-primario" href="${RAIZ}${encodeURI(no.u)}">Abrir página completa →</a>
        ${no.desc ? `<button type="button" data-acao="tudo">Mostrar todos os descendentes</button>` : ""}
        ${no.s ? `<a class="botao-sugerir" href="${esc(no.s)}" target="_blank" rel="noopener">✏️ Sugerir correção</a>` : ""}
        ${no.sf ? `<a class="botao-sugerir" href="${esc(no.sf)}" target="_blank" rel="noopener">➕ Acrescentar filho(a)</a>` : ""}
      </div>
      ${no.s ? `<p class="mini aviso-conta-mini">🔑 Os botões de sugestão pedem uma conta gratuita no GitHub. <a href="${RAIZ}sobre.html#contribuir">Como contribuir</a></p>` : ""}`;
    painel.hidden = false;
  }

  painel.addEventListener("click", (e) => {
    const pular = e.target.closest("[data-pular]");
    if (pular) { e.preventDefault(); irPara(pular.dataset.pular); return; }
    if (e.target.closest("[data-acao=tudo]") && selecionado) {
      (function abrir(n) { if ((n.k || []).length) { n.aberto = true; n.k.forEach(abrir); } })(selecionado);
      elementos.forEach((_, id) => atualizarBotao(porId.get(id)));
      desenhar(selecionado);
    }
  });

  // ----------------------------------------------------- zoom e deslocamento
  function aplicarVista() { camada.setAttribute("transform", `translate(${vista.x},${vista.y}) scale(${vista.k})`); }
  function animarVista(alvo) {
    const ini = { ...vista }, t0 = performance.now();
    const passo = (agora) => {
      const t = Math.min(1, (agora - t0) / DUR), e = 1 - Math.pow(1 - t, 3);
      vista = { x: ini.x + (alvo.x - ini.x) * e, y: ini.y + (alvo.y - ini.y) * e, k: ini.k + (alvo.k - ini.k) * e };
      aplicarVista();
      if (t < 1) requestAnimationFrame(passo);
    };
    requestAnimationFrame(passo);
  }
  function centralizar(no, suave, escala) {
    const r = svg.getBoundingClientRect();
    const k = escala || vista.k;
    // mostra a pessoa e o andar de cima (os filhos que acabaram de abrir)
    const alvo = { k, x: r.width / 2 - no.tx * k, y: r.height * 0.62 - (no.ty - (no.aberto ? PASSO_Y / 2 : 0)) * k };
    suave ? animarVista(alvo) : (vista = alvo, aplicarVista());
  }
  function ajustar(suave = true) {
    layout();
    const vis = visiveis(raiz);
    const xs = vis.map((n) => n.tx), ys = vis.map((n) => n.ty);
    const minX = Math.min(...xs) - LARG, maxX = Math.max(...xs) + LARG;
    const minY = Math.min(...ys) - ALT * 1.5, maxY = 170;
    const r = svg.getBoundingClientRect();
    const k = Math.max(0.25, Math.min(1.15, r.width / (maxX - minX), r.height / (maxY - minY)));
    const alvo = { k, x: r.width / 2 - ((minX + maxX) / 2) * k, y: r.height / 2 - ((minY + maxY) / 2) * k };
    suave ? animarVista(alvo) : (vista = alvo, aplicarVista());
  }
  function zoom(fator, cx, cy) {
    const r = svg.getBoundingClientRect();
    cx = cx ?? r.width / 2; cy = cy ?? r.height / 2;
    const k = Math.max(0.2, Math.min(2.5, vista.k * fator));
    vista = { k, x: cx - (cx - vista.x) * (k / vista.k), y: cy - (cy - vista.y) * (k / vista.k) };
    aplicarVista();
  }
  svg.addEventListener("wheel", (e) => {
    e.preventDefault();
    const r = svg.getBoundingClientRect();
    zoom(e.deltaY < 0 ? 1.12 : 1 / 1.12, e.clientX - r.left, e.clientY - r.top);
  }, { passive: false });
  let arraste = null;
  svg.addEventListener("pointerdown", (e) => {
    if (e.target.closest(".no")) return;
    arraste = { x: e.clientX, y: e.clientY, vx: vista.x, vy: vista.y };
    svg.setPointerCapture(e.pointerId);
    svg.classList.add("arrastando");
  });
  svg.addEventListener("pointermove", (e) => {
    if (!arraste) return;
    vista.x = arraste.vx + e.clientX - arraste.x; vista.y = arraste.vy + e.clientY - arraste.y;
    aplicarVista();
  });
  svg.addEventListener("pointerup", () => { arraste = null; svg.classList.remove("arrastando"); });

  document.querySelectorAll("[data-ferramenta]").forEach((b) => b.addEventListener("click", () => {
    const f = b.dataset.ferramenta;
    if (f === "mais") zoom(1.25);
    if (f === "menos") zoom(1 / 1.25);
    if (f === "ajustar") ajustar();
    if (f === "expandir" || f === "recolher") {
      porId.forEach((n) => { if ((n.k || []).length) n.aberto = f === "expandir"; });
      raiz.aberto = true;
      elementos.forEach((_, id) => atualizarBotao(porId.get(id)));
      desenhar();
      setTimeout(() => ajustar(), DUR + 20);
    }
  }));

  // ------------------------------------------------------------- famílias
  function escolher(pasta, idPessoa) {
    const f = DADOS.find((d) => d.pasta === pasta) || DADOS[0];
    familia = f;
    abas.querySelectorAll("button").forEach((b) => b.setAttribute("aria-selected", b.dataset.pasta === f.pasta));
    gNos.innerHTML = ""; gLinks.innerHTML = ""; gChao.innerHTML = ""; elementos.clear(); porId.clear();
    document.getElementById("vazio").hidden = !!f.raiz;
    document.getElementById("gif-familia").innerHTML = f.gif
      ? `<img src="${RAIZ}${encodeURI(f.gif)}" alt="Animação da árvore da família ${esc(f.sobrenome)}"><figcaption>A árvore ${esc(f.sobrenome)} crescendo, geração por geração.</figcaption>` : "";
    legenda.innerHTML = Array.from({ length: f.geracoes || 1 }, (_, i) =>
      `<li><span style="background:${cor(i + 1)[0]};border-color:${cor(i + 1)[1]}"></span>${i + 1}ª ${["fundador", "filhos", "netos", "bisnetos", "trinetos", "tetranetos", "pentanetos"][i] || ""}</li>`).join("");
    if (!f.raiz) { painel.hidden = true; return; }
    raiz = f.raiz;
    preparar(raiz, null);
    raiz.aberto = true;
    const alvo = idPessoa && porId.get(idPessoa);
    if (alvo) abrirAte(alvo);
    selecionado = alvo || raiz;
    mostrarPainel(selecionado);
    desenhar();
    if (alvo) setTimeout(() => centralizar(alvo, false, 0.9), 0); else ajustar(false);
  }
  function irPara(chave) {
    const [pasta, id] = chave.split("/");
    if (!familia || pasta !== familia.pasta) { escolher(pasta, id); return; }
    const no = porId.get(id);
    if (!no) return;
    abrirAte(no);
    selecionado = no;
    mostrarPainel(no);
    elementos.forEach((_, i) => atualizarBotao(porId.get(i)));
    desenhar(no);
    history.replaceState(null, "", `#${pasta}/${id}`);
  }

  abas.innerHTML = DADOS.map((f, i) =>
    `<button type="button" role="tab" data-pasta="${esc(f.pasta)}" style="--p:${CORES[i % CORES.length][0]};--c:${CORES[i % CORES.length][1]}">
       <strong>${esc(f.sobrenome)}</strong><small>${f.pessoas} pessoas</small></button>`).join("");
  abas.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-pasta]");
    if (b) { escolher(b.dataset.pasta); history.replaceState(null, "", "#" + b.dataset.pasta); }
  });
  let espera;
  window.addEventListener("resize", () => {
    clearTimeout(espera);
    espera = setTimeout(() => selecionado && selecionado !== raiz ? centralizar(selecionado, false) : ajustar(false), 150);
  });

  const [pasta, id] = decodeURIComponent(location.hash.slice(1)).split("/");
  escolher(pasta, id);
})();
