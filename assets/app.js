// Busca instantânea, visualizador de fotos e controles da árvore.
// Funciona abrindo os arquivos direto do disco (file://), sem servidor.
(function () {
  "use strict";
  const RAIZ = window.RAIZ || "";
  const PESSOAS = window.PESSOAS || [];
  const norm = (s) => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const indice = PESSOAS.map((p) => ({ p, chave: norm([p.n, p.f, p.c, p.a].join(" ")) }));

  // ---- Busca
  const campo = document.getElementById("busca");
  const lista = document.getElementById("resultados");
  if (campo && lista) {
    let ativo = -1;
    const mostrar = () => {
      const termos = norm(campo.value).split(/\s+/).filter(Boolean);
      ativo = -1;
      if (!termos.length) { lista.hidden = true; return; }
      const achados = indice.filter((i) => termos.every((t) => i.chave.includes(t))).slice(0, 30);
      lista.innerHTML = achados.length
        ? achados.map(({ p }) =>
            `<li><a href="${RAIZ}${encodeURI(p.u)}"><strong>${esc(p.n)}</strong> ${p.y ? `<span class="anos">${esc(p.y)}</span>` : ""}` +
            `<small>${esc(p.f)}${p.a ? " · filho(a) de " + esc(p.a.split(" › ").pop()) : ""}${p.c ? " · ⚭ " + esc(p.c) : ""}</small></a></li>`).join("")
        : `<li><small style="padding:.4rem .6rem;display:block">Nenhuma pessoa encontrada.</small></li>`;
      lista.hidden = false;
    };
    campo.addEventListener("input", mostrar);
    campo.addEventListener("keydown", (e) => {
      const links = [...lista.querySelectorAll("a")];
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        ativo = Math.max(0, Math.min(links.length - 1, ativo + (e.key === "ArrowDown" ? 1 : -1)));
        links.forEach((a, i) => a.classList.toggle("ativo", i === ativo));
      } else if (e.key === "Enter" && links.length) {
        location.href = links[Math.max(ativo, 0)].href;
      } else if (e.key === "Escape") {
        lista.hidden = true;
      }
    });
    document.addEventListener("click", (e) => { if (!e.target.closest(".busca")) lista.hidden = true; });
    document.addEventListener("keydown", (e) => {
      if (e.key === "/" && document.activeElement !== campo) { e.preventDefault(); campo.focus(); }
    });
  }

  // ---- Visualizador de fotos
  const visor = document.getElementById("visor");
  if (visor && visor.showModal) {
    const img = visor.querySelector("img"), legenda = visor.querySelector("p");
    document.querySelectorAll("a.foto").forEach((a) => a.addEventListener("click", (e) => {
      e.preventDefault();
      img.src = a.href;
      legenda.textContent = a.querySelector("img").alt;
      visor.showModal();
    }));
    visor.addEventListener("click", () => visor.close());
  }

  // ---- Expandir/recolher a árvore
  const todos = (aberto) => document.querySelectorAll(".arvore details").forEach((d) => (d.open = aberto));
  document.getElementById("expandir")?.addEventListener("click", () => todos(true));
  document.getElementById("recolher")?.addEventListener("click", () => todos(false));
})();
