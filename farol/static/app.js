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

// Kanban: arrastar cartão entre colunas persiste o status na hora.
(function kanban() {
  const board = document.querySelector("[data-board]");
  if (!board) return;

  let dragging = null;

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
      const status = column.dataset.status;
      const ticket = board.querySelector(`.ticket[data-id="${id}"]`);
      if (!ticket || !status) return;
      column.querySelector(".items").appendChild(ticket);
      updateCounts();
      try {
        const response = await fetch(`/candidaturas/${id}/status`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status }),
        });
        if (!response.ok) throw new Error(await response.text());
      } catch (error) {
        alert("Não consegui salvar o novo status. Recarregue a página.");
      }
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
        group.insertAdjacentHTML("beforeend", template.innerHTML);
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

// Confirmação em ações destrutivas — no formulário inteiro ou no botão que o enviou.
document.addEventListener("submit", (event) => {
  const message = event.submitter?.dataset.confirm || event.target.dataset.confirm;
  if (message && !window.confirm(message)) event.preventDefault();
});

// Coleta em segundo plano: mostra o indicador enquanto roda e recarrega a
// listagem quando termina. Quem dispara é a abertura do app (bin/farol-app) ou
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
