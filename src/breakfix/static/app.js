// La pagina: esercizi delle basi e ticket da /api, terminale vero da /ws/terminal.

// Il metodo di un sistemista, uguale per tutti i ticket: non dice la causa, dice da dove partire.
const FIRST_STEPS = [
  ["Riproduci il problema", "gestionale"],
  ["Dove sta il comando", "which gestionale"],
  ["Cosa avvia e con quale utente", 'cat "$(which gestionale)"'],
  ["Le unità dei servizi (dicono dove va il log)", "ls -l /etc/systemd/system/"],
  ["Processi per memoria occupata", "ps aux --sort=-rss | head"],
  ["Limite di memoria del container", "cat /sys/fs/cgroup/memory.max"],
];

const EMPTY = {
  basi: "Le <b>basi</b>: lezioni brevi, ognuna con esercizi verificati, che preparano ai ticket. " +
    "Scegli un esercizio in alto e premi <b>Avvia</b>: la sandbox riparte sana e l'esercizio la prepara.",
  ticket: "Scegli un ticket in alto e premi <b>Avvia</b>: la sandbox riparte sana e viene rotta come " +
    "racconta il ticket.",
};

const $ = (id) => document.getElementById(id);
let tickets = [];
let lessons = [];
let current = null; // quello che è in corso nella sandbox: un ticket o un esercizio
let tab = "basi";
let hintsShown = 0;
let socket = null;

// --- API -------------------------------------------------------------------------

async function api(path, method = "GET", body = undefined) {
  const options = { method };
  if (body !== undefined) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || response.statusText);
  return data;
}

// --- Testo -------------------------------------------------------------------------

function escape(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

const attr = (text) => escape(text).replace(/"/g, "&quot;");

// Indizi e testi usano i backtick per i comandi, ** e * per grassetto e corsivo, come il markdown.
function withCode(text) {
  return escape(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/\*([^*]+)\*/g, "<i>$1</i>");
}

// Le spiegazioni delle lezioni: un markdown minimo (titoli ##, paragrafi, elenchi, blocchi ```).
// I blocchi ```prova diventano pulsanti che eseguono il comando nel terminale.
function markdown(text) {
  const lines = text.replace(/\r/g, "").split("\n");
  const html = [];
  let i = 0;
  const special = (line) => /^(```|## |- |\d+\. )/.test(line) || !line.trim();
  while (i < lines.length) {
    const line = lines[i];
    const fence = line.match(/^```(\w*)/);
    if (fence) {
      const body = [];
      for (i += 1; i < lines.length && !lines[i].startsWith("```"); i += 1) body.push(lines[i]);
      i += 1;
      html.push(fence[1] === "prova"
        ? `<div class="steps">${body.filter((c) => c.trim()).map((c) =>
          `<button data-command="${attr(c)}">${escape(c)}</button>`).join("")}</div>`
        : `<pre>${escape(body.join("\n"))}</pre>`);
    } else if (line.startsWith("## ")) {
      html.push(`<h3>${withCode(line.slice(3))}</h3>`);
      i += 1;
    } else if (/^(- |\d+\. )/.test(line)) {
      const ordered = /^\d/.test(line);
      const items = [];
      for (; i < lines.length && /^(- |\d+\. )/.test(lines[i]); i += 1) {
        items.push(`<li>${withCode(lines[i].replace(/^(- |\d+\. )/, ""))}</li>`);
      }
      html.push(ordered ? `<ol>${items.join("")}</ol>` : `<ul>${items.join("")}</ul>`);
    } else if (!line.trim()) {
      i += 1;
    } else {
      const paragraph = [];
      for (; i < lines.length && !special(lines[i]); i += 1) paragraph.push(lines[i]);
      html.push(`<p>${withCode(paragraph.join(" "))}</p>`);
    }
  }
  return html.join("");
}

function showError(message) {
  $("error").textContent = message;
  $("error").hidden = !message;
}

// --- Schede e scelta -----------------------------------------------------------------

function fillPicker() {
  $("picker-label").textContent = tab === "basi" ? "Esercizio" : "Ticket";
  $("picker").innerHTML = tab === "basi"
    ? lessons.map((l) => `<optgroup label="${attr(`${l.number}. ${l.title} (${l.track})`)}">` +
      l.exercises.map((e) => `<option value="${e.key}">${e.key} ${escape(e.title)}</option>`).join("") +
      "</optgroup>").join("")
    : tickets.map((s) =>
      `<option value="${s.number}">${s.number}. ${escape(s.subject)} (${s.category}, ${s.difficulty})</option>`).join("");
}

// La scheda decide cosa si sceglie in alto; a sinistra si vede quello che è in corso, se è di quella scheda.
function setTab(name, selected = null) {
  tab = name;
  for (const button of document.querySelectorAll(".tabs button")) {
    button.setAttribute("aria-selected", String(button.dataset.tab === tab));
  }
  fillPicker();
  if (selected) $("picker").value = selected;
  const visible = Boolean(current) && (current.kind === "ticket") === (tab === "ticket");
  $("active").hidden = !visible;
  $("empty").hidden = visible;
  const running = current ? (current.kind === "ticket" ? "un ticket" : "un esercizio") : "";
  $("empty").innerHTML = EMPTY[tab] +
    (current && !visible ? `<br><br>Nella sandbox c'è ${running} in corso: <b>Avvia</b> lo chiude e riparte da capo.` : "");
}

// --- Ticket ed esercizi ----------------------------------------------------------------

function render(view) {
  current = view;
  hintsShown = 0;
  $("verdict").hidden = true;
  $("next").hidden = true;
  if (!view) {
    setTab(tab);
    return;
  }
  const isTicket = view.kind === "ticket";
  $("ticket-view").hidden = !isTicket;
  $("exercise-view").hidden = isTicket;
  if (isTicket) renderTicket(view);
  else renderExercise(view);
  setTab(isTicket ? "ticket" : "basi", isTicket ? String(view.number) : view.key);
  renderHints();
}

function renderTicket(view) {
  const t = view.ticket;
  $("ticket-number").textContent = `Ticket n. ${view.number}`;
  $("ticket-meta").textContent = `${view.category} · ${view.difficulty}`;
  $("ticket-sender").textContent = t.sender;
  $("ticket-subject").textContent = t.subject;
  $("ticket-body").textContent = t.body;
  $("ticket-helpdesk").innerHTML =
    `[Helpdesk] Programma: ${escape(t.program)} (si avvia con il comando <code>${escape(t.program)}</code>)<br>` +
    `[Helpdesk] Utente con cui gira: ${escape(t.user)}`;
  $("ticket-lessons").hidden = !view.lessons.length;
  $("ticket-lessons").innerHTML = "Per prepararti, nelle basi: " + view.lessons
    .map((l) => `<button class="link" data-lesson="${l.number}">lezione ${l.number}, ${escape(l.title)}</button>`)
    .join(" · ");
}

function renderExercise(view) {
  const lesson = view.lesson;
  $("lesson-heading").textContent = `Lezione ${lesson.number} · ${lesson.title}`;
  const prepares = lesson.tickets.length
    ? ` · prepara ${lesson.tickets.length > 1 ? "ai ticket" : "al ticket"} ${lesson.tickets.join(", ")}` : "";
  $("lesson-meta").textContent = `${lesson.track}${prepares}`;
  $("lesson-text").innerHTML = markdown(lesson.explanation);
  $("exercise-number").textContent =
    `Esercizio ${view.key} (${view.key.split(".")[1]} di ${lesson.exercises}) · ` +
    (view.type === "risposta" ? "trova la risposta sul sistema" : "cambia il sistema, poi verifica");
  $("exercise-title").textContent = view.title;
  $("exercise-task").innerHTML = markdown(view.task);
  $("answer-row").hidden = view.type !== "risposta";
  $("answer").value = "";
}

function renderHints() {
  const hints = current.hints;
  const man = current.kind === "ticket" ? current.man : current.lesson.man;
  $("hints").innerHTML = hints.slice(0, hintsShown)
    .map((hint, i) => `<p class="hint"><b>Indizio ${i + 1}/${hints.length}.</b> ${withCode(hint)}</p>`)
    .join("");
  const done = hintsShown >= hints.length;
  $("next-hint").hidden = done;
  $("next-hint").textContent = `Mostra indizio ${hintsShown + 1}/${hints.length}`;
  $("man").hidden = !done;
  $("man").textContent = `Man page utili: ${man.join(", ")}`;
}

// Dopo un esercizio riuscito: il successivo della lezione, o il ticket a cui la lezione prepara.
function offerNext() {
  const lesson = current.lesson;
  if (current.next) {
    $("next").textContent = `Esercizio successivo (${current.next}) →`;
    $("next").onclick = () => start("basi", current.next);
  } else if (lesson.tickets.length) {
    $("next").textContent = `Lezione finita: vai al ticket ${lesson.tickets[0]} →`;
    $("next").onclick = () => setTab("ticket", String(lesson.tickets[0]));
  } else {
    return;
  }
  $("next").hidden = false;
}

// --- Terminale ---------------------------------------------------------------------

const term = new Terminal({
  cursorBlink: true,
  fontFamily: '"Cascadia Mono", Consolas, ui-monospace, monospace',
  fontSize: 14,
  theme: { background: "#15181c" },
});
const fit = new FitAddon.FitAddon();
term.loadAddon(fit);
term.open($("terminal"));
fit.fit();

function send(message) {
  if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message));
}

function connect() {
  if (socket) {
    socket.onclose = null;
    socket.close();
  }
  term.reset();
  $("closed").hidden = true;
  const url = `ws://${location.host}/ws/terminal?cols=${term.cols}&rows=${term.rows}`;
  socket = new WebSocket(url);
  socket.binaryType = "arraybuffer";
  socket.onmessage = (event) =>
    term.write(typeof event.data === "string" ? event.data : new Uint8Array(event.data));
  socket.onclose = () => { $("closed").hidden = false; };
  term.focus();
}

term.onData((data) => send({ input: data }));
term.onResize(({ cols, rows }) => send({ resize: [cols, rows] }));
new ResizeObserver(() => fit.fit()).observe($("terminal"));

function runInTerminal(command) {
  send({ input: command + "\r" });
  term.focus();
}

// --- Azioni ------------------------------------------------------------------------

async function start(kind, value) {
  $("start").disabled = true;
  $("busy").hidden = false;
  showError("");
  try {
    render(await api(kind === "basi" ? `/api/learn/${value}` : `/api/start/${value}`, "POST"));
    connect(); // il container è nuovo: la vecchia shell non esiste più
  } catch (error) {
    showError(error.message);
  } finally {
    $("start").disabled = false;
    $("busy").hidden = true;
  }
}

async function check() {
  $("check").disabled = true;
  try {
    const isExercise = current.kind === "esercizio";
    const body = isExercise && current.type === "risposta" ? { answer: $("answer").value } : {};
    const result = await api("/api/check", "POST", body);
    const done = isExercise ? "corretto" : "riparato";
    $("verdict-status").className = `verdict ${result.passed ? "pass" : "fail"}`;
    $("verdict-status").textContent = result.passed ? `PASS: ${done}` : "FAIL: non ancora";
    $("verdict-output").textContent = result.output;
    $("verdict").hidden = false;
    if (result.passed && isExercise) offerNext();
  } catch (error) {
    showError(error.message);
  } finally {
    $("check").disabled = false;
  }
}

for (const button of document.querySelectorAll(".tabs button")) {
  button.onclick = () => setTab(button.dataset.tab);
}
$("start").onclick = () => start(tab, $("picker").value);
$("check").onclick = check;
$("answer").onkeydown = (event) => { if (event.key === "Enter") check(); };
$("next-hint").onclick = () => {
  hintsShown += 1;
  renderHints();
};
$("reconnect").onclick = connect;

// I comandi da provare nelle spiegazioni, e i rimandi dai ticket alle lezioni.
$("exercise-view").onclick = (event) => {
  const button = event.target.closest("button[data-command]");
  if (button) runInTerminal(button.dataset.command);
};
$("ticket-lessons").onclick = (event) => {
  const button = event.target.closest("button[data-lesson]");
  if (button) setTab("basi", `${button.dataset.lesson}.1`);
};

for (const [label, command] of FIRST_STEPS) {
  const button = document.createElement("button");
  button.textContent = command;
  button.title = label;
  button.onclick = () => runInTerminal(command);
  $("steps").append(button);
}

// --- Avvio della pagina --------------------------------------------------------------

(async () => {
  try {
    [tickets, lessons] = await Promise.all([api("/api/scenarios"), api("/api/lessons")]);
    const active = await api("/api/active");
    render(active);
    if (active) connect(); // pagina ricaricata con un ticket o un esercizio già avviato
    else term.write("Avvia un esercizio o un ticket: qui si apre la shell di root sul server.\r\n");
  } catch (error) {
    showError(`Server non raggiungibile: ${error.message}`);
  }
})();
