// Farol — JS mínimo: tema, kanban, campos repetíveis e confirmações.

(function theme() {
  const saved = localStorage.getItem("farol-theme");
  if (saved) document.documentElement.dataset.theme = saved;

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-theme-toggle]");
    if (!button) return;
    const current =
      document.documentElement.dataset.theme ||
      (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("farol-theme", next);
  });
})();

// Barra lateral retrátil. O estado inicial já foi aplicado pelo script do <head>
// (evita o pisca-pisca); aqui ficam só o clique e o rótulo acessível.
(function nav() {
  const root = document.documentElement;

  function sync() {
    const aberta = root.dataset.nav !== "closed";
    document.querySelectorAll("[data-nav-toggle]").forEach((button) => {
      button.setAttribute("aria-expanded", String(aberta));
      const rotulo = aberta ? "Recolher a barra lateral" : "Expandir a barra lateral";
      button.title = rotulo;
      const texto = button.querySelector(".sr-only");
      if (texto) texto.textContent = rotulo;
    });
  }

  document.addEventListener("click", (event) => {
    if (!event.target.closest("[data-nav-toggle]")) return;
    const fechada = root.dataset.nav === "closed";
    if (fechada) delete root.dataset.nav;
    else root.dataset.nav = "closed";
    try {
      localStorage.setItem("farol-nav", fechada ? "open" : "closed");
    } catch {
      // sem localStorage o estado vale só para esta página; não é motivo de erro
    }
    sync();
    // a largura útil mudou: quem depende dela recalcula
    window.dispatchEvent(new Event("farol:layout"));
  });

  sync();
})();

// Pré-visualização do currículo: o documento é servido em tamanho real dentro do
// iframe e reduzido por transform, porque `zoom` não atravessa a fronteira do
// documento embutido. A escala depende da largura disponível, que muda quando a
// barra lateral recolhe ou a janela é redimensionada.
(function resumePreview() {
  const frames = document.querySelectorAll(".pdf-preview iframe");
  if (!frames.length) return;

  function fit(frame) {
    const box = frame.parentElement;
    const largura = box.clientWidth;
    if (!largura) return;
    const real = frame.offsetWidth || 794; // 210mm
    const escala = largura / real;
    let altura = 1123; // 297mm, enquanto o conteúdo não carregou
    try {
      const corpo = frame.contentDocument && frame.contentDocument.body;
      if (corpo) altura = Math.max(corpo.scrollHeight, corpo.offsetHeight);
    } catch {
      // outro documento de origem diferente: fica na altura de uma página
    }
    frame.style.height = `${altura}px`;
    frame.style.transform = `scale(${escala})`;
    box.style.height = `${Math.round(altura * escala)}px`;
    box.classList.add("ready");
  }

  frames.forEach((frame) => {
    const refit = () => fit(frame);
    frame.addEventListener("load", refit);
    if (frame.contentDocument && frame.contentDocument.readyState === "complete") refit();
    window.addEventListener("resize", refit);
    window.addEventListener("farol:layout", refit);
    // a transição da barra lateral dura ~160ms; remede depois que ela termina
    window.addEventListener("farol:layout", () => window.setTimeout(refit, 200));
  });
})();

// Kanban: arrastar cartão entre colunas persiste o status na hora. O seletor de
// etapa dentro do cartão faz o mesmo pelo teclado e no celular, onde arrastar
// simplesmente não existe.
(function kanban() {
  const board = document.querySelector("[data-board]");
  if (!board) return;

  let dragging = null;

  async function persistOrder(column) {
    const ordem = [...column.querySelectorAll(".ticket")].map((t) => Number(t.dataset.id));
    if (!ordem.length) return;
    try {
      await fetch(`/candidaturas/${ordem[0]}/ordem`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ordem }),
      });
    } catch {
      // ordem é conforto, não dado: falhar aqui não merece interromper ninguém
    }
  }

  async function move(id, status, ticket) {
    const column = board.querySelector(`[data-status="${status}"]`);
    if (!column || !ticket) return;
    const origem = ticket.closest("[data-status]");
    column.querySelector(".items").appendChild(ticket);
    updateCounts();
    try {
      const response = await fetch(`/candidaturas/${id}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      if (!response.ok) throw new Error(await response.text());
    } catch {
      // devolve o cartão para onde estava: mentir sobre o estado salvo é pior
      // que a falha em si
      if (origem) origem.querySelector(".items").appendChild(ticket);
      updateCounts();
      const seletor = ticket.querySelector("[data-move]");
      if (seletor && origem) seletor.value = origem.dataset.status;
      warn("Não consegui salvar a etapa. Confira se o Farol ainda está rodando.");
    }
  }

  function warn(text) {
    // sem alert(): ele bloqueia a página inteira até alguém clicar
    let bar = document.querySelector(".flash.warn[data-live]");
    if (!bar) {
      bar = document.createElement("div");
      bar.className = "flash warn";
      bar.dataset.live = "1";
      document.querySelector(".main").insertBefore(bar, document.querySelector(".content"));
    }
    bar.textContent = text;
  }

  board.addEventListener("change", (event) => {
    const seletor = event.target.closest("[data-move]");
    if (!seletor) return;
    move(seletor.dataset.move, seletor.value, seletor.closest(".ticket"));
  });

  board.addEventListener("dragstart", (event) => {
    const ticket = event.target.closest(".ticket");
    if (!ticket) return;
    dragging = ticket;
    ticket.classList.add("dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", ticket.dataset.id);
  });

  board.addEventListener("dragend", () => {
    if (dragging) dragging.classList.remove("dragging");
    dragging = null;
    board.querySelectorAll(".col.over").forEach((col) => col.classList.remove("over"));
  });

  board.querySelectorAll("[data-status]").forEach((column) => {
    column.addEventListener("dragover", (event) => {
      event.preventDefault();
      column.classList.add("over");
    });
    column.addEventListener("dragleave", () => column.classList.remove("over"));
    column.addEventListener("drop", async (event) => {
      event.preventDefault();
      column.classList.remove("over");
      const id = event.dataTransfer.getData("text/plain");
      const ticket = board.querySelector(`.ticket[data-id="${id}"]`);
      if (!ticket) return;
      const mesmaColuna = ticket.closest("[data-status]") === column;
      const seletor = ticket.querySelector("[data-move]");
      if (seletor) seletor.value = column.dataset.status;

      // soltar sobre um cartão insere antes dele; soltar no vazio vai para o fim
      const alvo = event.target.closest(".ticket");
      const itens = column.querySelector(".items");
      if (alvo && alvo !== ticket) itens.insertBefore(ticket, alvo);
      else itens.appendChild(ticket);
      updateCounts();

      if (!mesmaColuna) await move(id, column.dataset.status, ticket);
      persistOrder(column);
    });
  });

  function updateCounts() {
    board.querySelectorAll("[data-status]").forEach((column) => {
      const badge = column.querySelector(".count");
      if (badge) badge.textContent = column.querySelectorAll(".ticket").length;
    });
  }
})();

// Campos repetíveis do perfil (experiência, projetos, formação, links, idiomas).
(function repeaters() {
  document.addEventListener("click", (event) => {
    const add = event.target.closest("[data-add]");
    if (add) {
      const group = document.querySelector(`[data-group="${add.dataset.add}"]`);
      const template = document.querySelector(`#tpl-${add.dataset.add}`);
      if (group && template) {
        // `__i__` (blocos da oficina) vira um índice único; no perfil não há o que trocar
        group.insertAdjacentHTML(
          "beforeend",
          template.innerHTML.replaceAll("__i__", `n${Date.now().toString(36)}`),
        );
        const last = group.lastElementChild.querySelector("input, textarea");
        if (last) last.focus();
      }
      return;
    }
    const remove = event.target.closest("[data-remove]");
    if (remove) {
      const item = remove.closest(".repeat-item");
      if (item) item.remove();
    }
  });
})();

// Oficina de currículo: a folha e a nota ATS acompanham a digitação. Quem
// desenha é o servidor, com o mesmo template da impressão — o navegador só
// troca o <article> dentro do iframe, então não existe uma segunda versão do
// currículo em JS para divergir da que vira PDF.
(function oficina() {
  const form = document.querySelector("[data-oficina]");
  if (!form) return;

  const frame = form.querySelector("[data-live-sheet]");
  const atsBox = form.querySelector("[data-live-ats]");
  const badge = form.querySelector("[data-ats-badge]");
  const state = form.querySelector("[data-live-state]");
  const dirtyFlag = document.querySelector("[data-dirty-flag]");
  let timer = 0;
  let controller = null;
  let dirty = false;

  function setState(text, kind) {
    if (!state) return;
    state.textContent = text;
    state.classList.toggle("busy", kind === "busy");
    state.classList.toggle("off", kind === "off");
  }

  // O anel não pula de 62 para 78: desenha o caminho, e o número conta junto.
  function tween(box, from) {
    const ring = box.querySelector(".ats-ring .value");
    const num = box.querySelector("[data-ats-num]");
    const to = Number(box.firstElementChild?.dataset.atsScore || 0);
    if (!ring || !num || from === to || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    ring.style.transition = "none";
    ring.setAttribute("stroke-dasharray", `${from} 100`);
    ring.getBoundingClientRect(); // força o navegador a assumir o ponto de partida
    ring.style.transition = "";
    ring.setAttribute("stroke-dasharray", `${to} 100`);
    const start = performance.now();
    (function step(now) {
      const t = Math.min(1, (now - start) / 500);
      num.textContent = Math.round(from + (to - from) * t);
      if (t < 1) requestAnimationFrame(step);
    })(start);
  }

  async function refresh() {
    controller?.abort();
    controller = new AbortController();
    setState("atualizando…", "busy");
    try {
      const response = await fetch(form.dataset.live, {
        method: "POST",
        body: new FormData(form),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(String(response.status));
      const data = await response.json();

      const sheet = frame?.contentDocument?.querySelector("article.sheet");
      if (sheet) {
        sheet.outerHTML = data.sheet;
        frame.dispatchEvent(new Event("load")); // remede a altura (ver resumePreview)
      }
      if (atsBox) {
        const from = Number(atsBox.firstElementChild?.dataset.atsScore || 0);
        const open = atsBox.querySelector("details")?.open;
        atsBox.innerHTML = data.ats;
        if (open) atsBox.querySelector("details").open = true;
        tween(atsBox, from);
      }
      if (badge) {
        badge.textContent = data.score;
        badge.className = `ats-badge g-${data.grade}`;
      }
      setState(dirty ? "ao vivo · não salvo" : "ao vivo", "");
    } catch (error) {
      if (error.name === "AbortError") return;
      setState("sem resposta do app — a folha mostra a última versão", "off");
    }
  }

  function touch() {
    dirty = true;
    if (dirtyFlag) dirtyFlag.hidden = false;
    window.clearTimeout(timer);
    timer = window.setTimeout(refresh, 320);
  }

  form.addEventListener("input", touch);
  form.addEventListener("change", touch);
  // adicionar e remover bloco não disparam `input`; o DOM já mudou quando isto roda
  form.addEventListener("click", (event) => {
    if (event.target.closest("[data-add], [data-remove]")) window.setTimeout(touch, 0);
  });

  // o texto de ajuda acompanha o modelo escolhido
  const hints = JSON.parse(document.querySelector("#tpl-hints")?.textContent || "{}");
  const hint = form.querySelector("[data-tpl-hint]");
  form.addEventListener("change", (event) => {
    if (event.target.name === "template" && hint) hint.textContent = hints[event.target.value]?.hint || "";
  });

  // Sair com edição não salva pede confirmação — a folha ao vivo dá a impressão
  // de que tudo já está guardado, e não está. Enviar o formulário não pergunta.
  form.addEventListener("submit", (event) => {
    // depois dos outros ouvintes: se a confirmação cancelou o envio, continua não salvo
    window.setTimeout(() => { if (!event.defaultPrevented) dirty = false; }, 0);
  });
  window.addEventListener("beforeunload", (event) => {
    if (dirty) event.preventDefault();
  });
})();

// "Criar a partir de um currículo pronto": o currículo de origem está na URL da
// ação, então o seletor reescreve o destino do botão.
(function derive() {
  const form = document.querySelector("[data-derive]");
  if (!form) return;
  const base = form.querySelector("[data-derive-base]");
  const button = form.querySelector("[data-derive-go]");
  const sync = () => button.setAttribute("formaction", `/curriculos/${base.value}/derivar`);
  base.addEventListener("change", sync);
  sync();
})();

// Abas do painel da oficina (Folha | Verificador ATS). Sem JS os dois painéis
// ficam abertos em sequência; com JS um se esconde e as setas navegam.
(function tabs() {
  document.querySelectorAll("[data-tabs]").forEach((root) => {
    const buttons = [...root.querySelectorAll("[data-tab]")];
    const panels = [...root.querySelectorAll("[data-panel]")];
    if (!buttons.length) return;
    root.classList.add("on");

    function select(name, focus) {
      buttons.forEach((button) => {
        const active = button.dataset.tab === name;
        button.setAttribute("aria-selected", String(active));
        button.tabIndex = active ? 0 : -1;
        if (active && focus) button.focus();
      });
      panels.forEach((panel) => { panel.hidden = panel.dataset.panel !== name; });
      // a folha mede a própria altura, e escondida ela mede zero
      if (name === "folha") window.dispatchEvent(new Event("farol:layout"));
      try { sessionStorage.setItem("farol-oficina-aba", name); } catch { /* modo privado */ }
    }

    buttons.forEach((button, index) => {
      button.addEventListener("click", () => select(button.dataset.tab, false));
      button.addEventListener("keydown", (event) => {
        const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
        if (!step) return;
        event.preventDefault();
        select(buttons[(index + step + buttons.length) % buttons.length].dataset.tab, true);
      });
    });

    let saved = "";
    try { saved = sessionStorage.getItem("farol-oficina-aba") || ""; } catch { /* modo privado */ }
    select(buttons.some((b) => b.dataset.tab === saved) ? saved : buttons[0].dataset.tab, false);
  });
})();

// Confirmação em ações destrutivas — no formulário inteiro ou no botão que o enviou.
document.addEventListener("submit", (event) => {
  const message = event.submitter?.dataset.confirm || event.target.dataset.confirm;
  if (message && !window.confirm(message)) event.preventDefault();
});

// Coleta em segundo plano: mostra o indicador enquanto roda e recarrega a
// listagem quando termina. Quem dispara é a abertura do app (farol.launcher) ou
// o botão "Atualizar vagas".
(function collectWatcher() {
  const chip = document.querySelector("[data-collect]");
  if (!chip) return;

  const reloads = document.querySelector("[data-reload-on-collect]");
  const startedAt = Date.now();
  let sawRunning = !chip.hidden;

  async function check() {
    let state;
    try {
      const response = await fetch("/coleta/status", { cache: "no-store" });
      state = await response.json();
    } catch {
      return schedule(); // servidor reiniciando: tenta de novo
    }

    chip.hidden = !state.running;
    if (state.running) {
      sawRunning = true;
      return schedule();
    }

    if (sawRunning) {
      const novas = state.report ? state.report.new : 0;
      const falhas = state.report
        ? state.report.sources.filter((source) => source.status !== "ok")
        : [];
      if (reloads) {
        const url = new URL(window.location.href);
        url.searchParams.set(
          "msg",
          state.error
            ? `A coleta falhou: ${state.error}`
            : `Coleta concluída: ${novas} vaga(s) nova(s)` +
              (state.report && state.report.expired
                ? ` · ${state.report.expired} saíram do ar`
                : "") +
              (falhas.length ? ` · falharam: ${falhas.map((f) => f.label).join(", ")}` : "."),
        );
        url.searchParams.set("tone", state.error || falhas.length ? "warn" : "ok");
        window.location.replace(url.toString());
      }
      return;
    }

    // a coleta da abertura pode demorar um instante para começar
    if (Date.now() - startedAt < 15000) schedule();
  }

  function schedule() {
    window.setTimeout(check, 2500);
  }

  check();
})();

// Filtros da lista de vagas aplicam ao mudar, sem botão.
document.querySelectorAll("[data-autosubmit]").forEach((element) => {
  element.addEventListener("change", () => element.form.submit());
});

// Busca de artigos em segundo plano. Mesmo desenho do observador da coleta, com
// uma diferença que importa: aqui a rodada só começa por pedido explícito, então
// não há o caso de "pode estar prestes a começar".
(function readingWatcher() {
  const page = document.querySelector("[data-reload-on-reading]");
  if (!page) return;

  let sawRunning = false;

  async function check() {
    let state;
    try {
      const response = await fetch("/leituras/status", { cache: "no-store" });
      state = await response.json();
    } catch {
      return; // servidor reiniciando: a página segue utilizável como está
    }
    if (state.running) {
      sawRunning = true;
      return window.setTimeout(check, 2000);
    }
    if (!sawRunning) return;

    const url = new URL(window.location.href);
    const novos = state.report ? state.report.new : 0;
    const falhas = state.report ? state.report.feeds.filter((f) => f.status !== "ok") : [];
    url.searchParams.set(
      "msg",
      state.error
        ? `A busca falhou: ${state.error}`
        : `${novos} artigo(s) novo(s)` +
          (falhas.length ? ` · falharam: ${falhas.map((f) => f.label).join(", ")}` : "."),
    );
    url.searchParams.set("tone", state.error || falhas.length ? "warn" : "ok");
    window.location.replace(url.toString());
  }

  check();
})();

// Ajustes → assistente de IA: troca do provedor e consulta ao servidor local.
// O botão pergunta ao servidor quais modelos ele tem; nada é instalado nem
// baixado daqui, e a recusa de endereço público vem do próprio servidor do app.
(function localAI() {
  const seletor = document.querySelector("[data-ai-provider]");
  if (!seletor) return;

  const blocos = document.querySelectorAll("[data-ia-bloco]");
  function sync() {
    blocos.forEach((bloco) => {
      bloco.hidden = bloco.dataset.iaBloco !== seletor.value;
    });
  }
  seletor.addEventListener("change", sync);
  sync();

  const botao = document.querySelector("[data-ia-detectar]");
  const sonda = document.querySelector("[data-ia-sonda]");
  const lista = document.querySelector("[data-ia-lista]");
  const campoUrl = document.querySelector("#local_ai_url");
  if (!botao || !sonda) return;

  botao.addEventListener("click", async () => {
    sonda.hidden = false;
    sonda.className = "sonda";
    sonda.textContent = "Perguntando ao servidor…";
    botao.disabled = true;
    let dados;
    try {
      const response = await fetch("/ajustes/ia/modelos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ endpoint: campoUrl ? campoUrl.value : "" }),
      });
      dados = await response.json();
    } catch (erro) {
      sonda.className = "sonda bad";
      sonda.textContent = `Não consegui perguntar: ${erro}`;
      botao.disabled = false;
      return;
    }
    botao.disabled = false;

    if (!dados.ok) {
      sonda.className = "sonda bad";
      sonda.textContent = dados.erro;
      return;
    }
    if (lista) {
      lista.innerHTML = "";
      dados.models.forEach((modelo) => {
        const opcao = document.createElement("option");
        opcao.value = modelo.name;
        opcao.label = [modelo.params, modelo.size_gb ? `${modelo.size_gb} GB` : ""]
          .filter(Boolean)
          .join(" · ");
        lista.appendChild(opcao);
      });
    }
    if (!dados.models.length) {
      sonda.textContent = `${dados.endpoint} respondeu, mas não tem modelo instalado.`;
      return;
    }
    sonda.innerHTML = `<b>${dados.models.length} modelo(s)</b> em ${dados.endpoint}:`;
    const ul = document.createElement("ul");
    dados.models.forEach((modelo) => {
      const li = document.createElement("li");
      const detalhe = [modelo.params, modelo.size_gb ? `${modelo.size_gb} GB` : ""]
        .filter(Boolean)
        .join(" · ");
      li.textContent = detalhe ? `${modelo.name} — ${detalhe}` : modelo.name;
      ul.appendChild(li);
    });
    sonda.appendChild(ul);
  });
})();
