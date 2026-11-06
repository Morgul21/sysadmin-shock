// La pagina: le mappe delle basi e delle challenge (box collegate), e la pagina di lavoro con il
// terminale. Gli indirizzi stanno nel frammento: #/basi, #/basi/5/2 (lezione 5, esercizio 2),
// #/challenge, #/challenge/3. Ricaricando si resta dove si era, e la sandbox riparte solo se
// l'esercizio o il ticket chiesto non è già quello attivo.

// Il metodo di un sistemista, uguale per tutti i ticket: non dice la causa, dice da dove partire.
const FIRST_STEPS = [
  ["Riproduci il problema", "gestionale"],
  ["Dove sta il comando", "which gestionale"],
  ["Cosa avvia e con quale utente", 'cat "$(which gestionale)"'],
  ["Le unità dei servizi (dicono dove va il log)", "ls -l /etc/systemd/system/"],
  ["Processi per memoria occupata", "ps aux --sort=-rss | head"],
  ["Limite di memoria del container", "cat /sys/fs/cgroup/memory.max"],
];

const TRACKS = { orientarsi: "Orientarsi", permessi: "Permessi", "processi e memoria": "Processi e memoria" };
const LEVELS = { facile: "Facili", media: "Medie", difficile: "Difficili" };

const INTRO = {
  basi: "Lezioni brevi, una per gruppo di comandi, ognuna con esercizi verificati: si seguono in ordine, " +
    "ma puoi aprire qualunque lezione. Aprendo una lezione la sandbox riparte da capo e si prepara per l'esercizio.",
  challenge: "Ticket veri, da risolvere senza che nessuno ti dica dove guardare. Il colore dice la difficoltà; " +
    "sotto, le lezioni delle basi che preparano. Aprendo un ticket la sandbox riparte da capo e viene rotta come racconta il ticket.",
};

const $ = (id) => document.getElementById(id);
let lessons = [];
let tickets = [];
let current = null; // quello che è attivo nella sandbox: un ticket o un esercizio
let hintsShown = 0;
let socket = null;
let busy = false;

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

// --- Progresso: nel browser, per chi usa questa macchina ----------------------------

const PROGRESS_KEY = "breakfix.progress";

function loadProgress() {
  try {
    const saved = JSON.parse(localStorage.getItem(PROGRESS_KEY)) || {};
    return { exercises: saved.exercises || [], tickets: saved.tickets || [] };
  } catch {
    return { exercises: [], tickets: [] };
  }
}

const progress = loadProgress();
const isDone = (kind, id) => progress[kind].includes(id);

function markDone(kind, id) {
  if (!isDone(kind, id)) progress[kind].push(id);
  try {
    localStorage.setItem(PROGRESS_KEY, JSON.stringify(progress));
  } catch {
    // senza storage il progresso vale solo fino al prossimo caricamento
  }
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
  for (const id of ["error", "map-error"]) {
    $(id).textContent = message;
    $(id).hidden = !message;
  }
}

// --- Le mappe: box collegate -----------------------------------------------------------

const arrow = '<span class="arrow" aria-hidden="true">→</span>';

function lessonBox(lesson, first) {
  // I comandi della lezione sono le sue man page di sezione 1 (comandi utente) e 8 (amministrazione).
  const commands = lesson.man.filter((m) => /\((1p?|8)\)$/.test(m)).map((m) => m.replace(/\(.*\)$/, ""));
  const marks = lesson.exercises
    .map((e) => `<span class="mark${isDone("exercises", e.key) ? " done" : ""}"></span>`).join("");
  const doneCount = lesson.exercises.filter((e) => isDone("exercises", e.key)).length;
  const complete = doneCount === lesson.exercises.length;
  return `<div class="node">${first ? "" : arrow}
    <a class="box${complete ? " complete" : ""}" href="#/basi/${lesson.number}">
      <span class="box-number">Lezione ${lesson.number}${complete ? " · completata" : ""}</span>
      <span class="box-title">${escape(lesson.title)}</span>
      <span class="box-commands">${commands.map((c) => `<code>${escape(c)}</code>`).join(" ")}</span>
      <span class="marks" title="${doneCount} esercizi su ${lesson.exercises.length}">${marks}</span>
    </a></div>`;
}

function ticketBox(ticket, first) {
  const done = isDone("tickets", ticket.number);
  const prepare = ticket.lessons.length
    ? `<span class="box-prepare">Preparati con: lezion${ticket.lessons.length > 1 ? "i" : "e"} ${ticket.lessons.join(", ")}</span>` : "";
  return `<div class="node">${first ? "" : arrow}
    <a class="box ticket ${ticket.difficulty}" href="#/challenge/${ticket.number}">
      <span class="box-number">Ticket ${ticket.number}${done ? " · risolto" : ""}</span>
      <span class="box-title">${escape(ticket.subject)}</span>
      <span><span class="badge ${ticket.difficulty}">${ticket.difficulty}</span>
        <span class="muted small">${escape(ticket.category)}</span></span>
      ${prepare}
    </a></div>`;
}

function section(title, boxes, className = "") {
  return boxes.length ? `<section class="track ${className}"><h2>${title}</h2><div class="path">${boxes.join("")}</div></section>` : "";
}

function showMap(kind) {
  $("work-page").hidden = true;
  $("map-page").hidden = false;
  $("map-intro").textContent = INTRO[kind];
  $("map").innerHTML = kind === "basi"
    ? Object.entries(TRACKS).map(([track, name]) =>
      section(name, lessons.filter((l) => l.track === track).map((l, i) => lessonBox(l, i === 0)))).join("")
    : Object.entries(LEVELS).map(([level, name]) =>
      section(name, tickets.filter((t) => t.difficulty === level).map((t, i) => ticketBox(t, i === 0)), level)).join("");
}

// --- La pagina di lavoro ------------------------------------------------------------

function showWork() {
  $("map-page").hidden = true;
  $("work-page").hidden = false;
  requestAnimationFrame(() => fit.fit()); // il terminale era nascosto: va ridimensionato ora
}

async function start(path) {
  if (busy) return;
  busy = true;
  showError("");
  showWork();
  $("work").hidden = true;
  $("loading").hidden = false;
  try {
    render(await api(path, "POST"));
    connect(); // il container è nuovo: la vecchia shell non esiste più
  } catch (error) {
    showError(error.message);
  } finally {
    busy = false;
    $("loading").hidden = true;
  }
}

async function openLesson(number, step) {
  const lesson = lessons.find((l) => l.number === number);
  if (!lesson) return void (location.hash = "#/basi");
  const key = step ? `${number}.${step}` : null;
  setBack("basi");
  if (current?.kind === "esercizio" && current.lesson.number === number && (!key || key === current.key)) {
    render(current);
    return;
  }
  // Senza un esercizio indicato, il primo non ancora superato.
  const target = key || (lesson.exercises.find((e) => !isDone("exercises", e.key)) || lesson.exercises[0]).key;
  await start(`/api/learn/${target}`);
}

async function openTicket(number) {
  if (!tickets.some((t) => t.number === number)) return void (location.hash = "#/challenge");
  setBack("challenge");
  if (current?.kind === "ticket" && current.number === number) {
    render(current);
    return;
  }
  await start(`/api/start/${number}`);
}

function setBack(kind) {
  $("back").href = `#/${kind}`;
  $("back").textContent = kind === "basi" ? "← Basi" : "← Challenge";
}

function render(view) {
  current = view;
  hintsShown = 0;
  $("verdict").hidden = true;
  $("next").hidden = true;
  $("next-ticket").hidden = true;
  const isTicket = view.kind === "ticket";
  $("exercise-view").hidden = isTicket;
  $("ticket-view").hidden = !isTicket;
  if (isTicket) renderTicket(view);
  else renderExercise(view);
  renderHints();
  $("tutor").hidden = !isTicket;
  if (isTicket) loadTutor();
  $("fixer").hidden = !isTicket;
  stopFixerPolling();
  if (isTicket) loadFixer();
  else renderFixer(null);
  $("work").hidden = false;
  // L'indirizzo segue quello che è attivo (es. il primo esercizio scelto in automatico).
  const hash = isTicket ? `#/challenge/${view.number}` : `#/basi/${view.lesson.number}/${view.key.split(".")[1]}`;
  if (location.hash !== hash) history.replaceState(null, "", hash);
  setTab(isTicket ? "challenge" : "basi");
  showWork();
}

function renderExercise(view) {
  const lesson = view.lesson;
  const entry = lessons.find((l) => l.number === lesson.number);
  $("lesson-heading").textContent = `Lezione ${lesson.number} · ${lesson.title}`;
  const prepares = lesson.tickets.length
    ? ` · prepara ${lesson.tickets.length > 1 ? "ai ticket" : "al ticket"} ${lesson.tickets.join(", ")}` : "";
  $("lesson-meta").textContent = `${TRACKS[lesson.track] || lesson.track}${prepares}`;
  $("lesson-text").innerHTML = markdown(lesson.explanation);
  // Aperta finché non hai superato nessun esercizio della lezione.
  $("lesson-explanation").open = !entry.exercises.some((e) => isDone("exercises", e.key));
  renderStepper(entry, view.key);
  $("exercise-number").textContent = `Esercizio ${view.key} · ` +
    (view.type === "risposta" ? "trova la risposta sul sistema" : "cambia il sistema, poi verifica");
  $("exercise-title").textContent = view.title;
  $("exercise-task").innerHTML = markdown(view.task);
  $("answer-row").hidden = view.type !== "risposta";
  $("answer").value = "";
}

// Il selettore: un trattino per esercizio. Un clic cambia l'indirizzo, e il router avvia l'esercizio.
function renderStepper(lesson, activeKey) {
  $("stepper").innerHTML = lesson.exercises.map((e, i) => {
    const state = (e.key === activeKey ? " active" : "") + (isDone("exercises", e.key) ? " done" : "");
    return `<a class="step${state}" href="#/basi/${lesson.number}/${i + 1}" title="${attr(`${e.key} ${e.title}`)}"` +
      `${e.key === activeKey ? ' aria-current="step"' : ""}><span class="dash"></span><span>${e.key}</span></a>`;
  }).join("");
}

function renderTicket(view) {
  const t = view.ticket;
  $("ticket-number").textContent = `Ticket n. ${view.number}`;
  $("ticket-meta").innerHTML = `<span class="badge ${view.difficulty}">${view.difficulty}</span> ` +
    `<span class="muted">${escape(view.category)}</span>`;
  $("ticket-sender").textContent = t.sender;
  $("ticket-subject").textContent = t.subject;
  $("ticket-body").textContent = t.body;
  $("ticket-helpdesk").innerHTML =
    `[Helpdesk] Programma: ${escape(t.program)} (si avvia con il comando <code>${escape(t.program)}</code>)<br>` +
    `[Helpdesk] Utente con cui gira: ${escape(t.user)}`;
  $("ticket-lessons").hidden = !view.lessons.length;
  $("ticket-lessons").innerHTML = "Per prepararti, nelle basi: " + view.lessons
    .map((l) => `<a href="#/basi/${l.number}">lezione ${l.number}, ${escape(l.title)}</a>`).join(" · ");
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

// --- Tutor: solo nei ticket. La conversazione la tiene il server, per sandbox: con un ticket nuovo riparte.

function tutorEntry({ question, answer, blocked }) {
  // Se il guardrail ha bloccato la risposta del modello, la pagina lo dice: è parte della demo.
  const note = blocked ? '<span class="tutor-note">Il guardrail ha fermato una risposta con la soluzione.</span>' : "";
  return `<p class="tutor-question">${escape(question)}</p>` +
    `<p class="tutor-answer${blocked ? " blocked" : ""}">${note}${withCode(answer)}</p>`;
}

async function loadTutor() {
  $("tutor-log").innerHTML = "";
  try {
    const transcript = await api("/api/tutor");
    $("tutor-log").innerHTML = transcript.map(tutorEntry).join("");
    $("tutor").open = transcript.length > 0;
  } catch {
    // senza conversazione il riquadro resta vuoto: la domanda dirà se il tutor non è raggiungibile
  }
}

async function askTutor(event) {
  event.preventDefault();
  const question = $("tutor-question").value.trim();
  if (!question) return;
  $("tutor-send").disabled = true;
  $("tutor-send").textContent = "Il tutor sta pensando…";
  const pending = document.createElement("p");
  pending.className = "tutor-question";
  pending.textContent = question;
  $("tutor-log").append(pending);
  try {
    const entry = await api("/api/tutor", "POST", { question, hints_shown: hintsShown });
    pending.remove();
    $("tutor-log").insertAdjacentHTML("beforeend", tutorEntry(entry));
    $("tutor-question").value = "";
  } catch (error) {
    pending.remove();
    showError(error.message);
  } finally {
    $("tutor-send").disabled = false;
    $("tutor-send").textContent = "Chiedi";
  }
}

// --- "Fallo risolvere all'AI": il fixer lavora sul server, la pagina ne segue i comandi ----------

const FIXER_POLL_MS = 1500;
let fixerTimer = null;

function fixerStep(step) {
  const tag = step.blocked
    ? '<span class="step-tag blocked">bloccato dal guardrail</span>'
    : step.exit_code === 0 ? '<span class="step-tag ok">ok</span>'
    : `<span class="step-tag error">${step.exit_code == null ? "rifiutato" : `errore ${step.exit_code}`}</span>`;
  const output = step.output ? `<pre>${escape(step.output)}</pre>` : '<pre class="muted">(nessun output)</pre>';
  return `<li class="${step.blocked ? "blocked" : ""}"><details><summary>${escape(step.command)}${tag}</summary>` +
    `${output}</details></li>`;
}

function renderFixer(run) {
  const running = run?.status === "running";
  $("fixer-start").disabled = running;
  $("fixer-start").textContent = running ? "L'AI sta lavorando…" : run ? "Fallo riprovare all'AI" : "Fallo risolvere all'AI";
  $("fixer-steps").innerHTML = (run?.steps || []).map(fixerStep).join("");
  $("fixer-status").hidden = !(running || run?.status === "error");
  if (running) {
    const n = run.steps.length;
    $("fixer-status").textContent = n ? `L'AI ha lanciato ${n} comand${n === 1 ? "o" : "i"} finora…`
      : "Riparto dalla sandbox rotta e l'AI legge il ticket…";
  } else if (run?.status === "error") {
    $("fixer-status").textContent = `L'AI non è arrivata al verdetto: ${run.error}`;
  }
  const result = run?.status === "done" ? run.result : null;
  $("fixer-result").hidden = !result;
  if (!result) return;
  $("fixer-verdict").className = `verdict ${result.passed ? "pass" : "fail"}`;
  $("fixer-verdict").textContent = result.passed
    ? "PASS: l'AI ha riparato il ticket (lo dice il controllo, non l'AI)"
    : "FAIL: l'AI non è riuscita a riparare il ticket";
  const blocked = result.blocked_by_guardrail ? `, ${result.blocked_by_guardrail} bloccati dal guardrail` : "";
  $("fixer-summary").textContent =
    `${result.tool_calls} comandi${blocked} · ${result.llm_calls} chiamate al modello · ${result.tokens} token · ` +
    `${result.duration_s} s · registro completo: .breakfix/audit/${result.audit}` +
    (result.error ? ` · l'AI si è fermata a metà: ${result.error}` : "");
  $("fixer-answer").hidden = !result.answer;
  $("fixer-answer").textContent = result.answer ? `Cosa dice di aver fatto l'AI:\n\n${result.answer}` : "";
}

function stopFixerPolling() {
  clearTimeout(fixerTimer);
  fixerTimer = null;
}

function pollFixer() {
  stopFixerPolling();
  fixerTimer = setTimeout(async () => {
    try {
      const run = await api("/api/fixer");
      renderFixer(run);
      if (run?.status === "running") return pollFixer();
      fixerTimer = null;
      connect(); // la sandbox è nuova: il terminale si riapre sulla macchina lasciata dall'AI
    } catch (error) {
      showError(error.message);
      pollFixer();
    }
  }, FIXER_POLL_MS);
}

async function loadFixer() {
  try {
    const run = await api("/api/fixer");
    renderFixer(run);
    $("fixer").open = $("fixer").open || Boolean(run);
    if (run?.status === "running") pollFixer();
  } catch {
    renderFixer(null);
  }
}

async function startFixer() {
  if (!confirm("La sandbox riparte rotta da capo e l'AI prova a ripararla da sola. " +
    "Quello che hai fatto nel terminale si perde. Procedo?")) return;
  showError("");
  $("verdict").hidden = true;
  $("fixer-start").disabled = true;
  try {
    renderFixer(await api("/api/fixer", "POST"));
    pollFixer();
  } catch (error) {
    showError(error.message);
    $("fixer-start").disabled = false;
  }
}

function showLink(id, text, href) {
  $(id).textContent = text;
  $(id).href = href;
  $(id).hidden = false;
}

// Dopo un esercizio riuscito: il successivo, o a fine lezione la lezione dopo e il ticket collegato.
function offerNext() {
  if (current.kind === "ticket") {
    const next = tickets.find((t) => t.number === current.number + 1);
    if (next) showLink("next", `Ticket successivo (${next.number}) →`, `#/challenge/${next.number}`);
    return;
  }
  const lesson = current.lesson;
  if (current.next) {
    showLink("next", `Esercizio successivo (${current.next}) →`, `#/basi/${lesson.number}/${current.next.split(".")[1]}`);
    return;
  }
  const following = lessons.find((l) => l.number > lesson.number);
  if (following) showLink("next", `Lezione successiva (${following.number}) →`, `#/basi/${following.number}`);
  if (lesson.tickets.length) {
    showLink("next-ticket", `Prova il ticket ${lesson.tickets[0]} →`, `#/challenge/${lesson.tickets[0]}`);
  }
}

async function check() {
  $("check").disabled = true;
  try {
    const isExercise = current.kind === "esercizio";
    const body = isExercise && current.type === "risposta" ? { answer: $("answer").value } : {};
    const result = await api("/api/check", "POST", body);
    $("verdict-status").className = `verdict ${result.passed ? "pass" : "fail"}`;
    $("verdict-status").textContent = result.passed ? `PASS: ${isExercise ? "corretto" : "riparato"}` : "FAIL: non ancora";
    $("verdict-output").textContent = result.output;
    $("verdict").hidden = false;
    if (result.passed) {
      if (isExercise) {
        markDone("exercises", current.key);
        renderStepper(lessons.find((l) => l.number === current.lesson.number), current.key);
      } else {
        markDone("tickets", current.number);
      }
      offerNext();
    }
  } catch (error) {
    showError(error.message);
  } finally {
    $("check").disabled = false;
  }
}

// --- Terminale ---------------------------------------------------------------------

const term = new Terminal({
  cursorBlink: true,
  fontFamily: '"Cascadia Mono", Consolas, ui-monospace, monospace',
  fontSize: 14,
  // Gli stessi toni della pagina (app.css): verde tenue su fondo verde-nero, cursore ambra.
  theme: {
    background: "#0a1311",
    foreground: "#a6cdb8",
    cursor: "#d9a441",
    cursorAccent: "#0a1311",
    selectionBackground: "#2f6e5c88",
  },
});
const fit = new FitAddon.FitAddon();
term.loadAddon(fit);
term.open($("terminal"));

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
new ResizeObserver(() => { if (!$("work-page").hidden) fit.fit(); }).observe($("terminal"));

function runInTerminal(command) {
  send({ input: command + "\r" });
  term.focus();
}

// --- Router ------------------------------------------------------------------------

function setTab(name) {
  for (const tab of document.querySelectorAll(".tabs a")) {
    if (tab.dataset.tab === name) tab.setAttribute("aria-current", "page");
    else tab.removeAttribute("aria-current");
  }
}

function route() {
  const [part, number, step] = location.hash.replace(/^#\/?/, "").split("/");
  const kind = part === "challenge" ? "challenge" : "basi";
  setTab(kind);
  showError("");
  if (!number) return showMap(kind);
  return kind === "basi" ? openLesson(Number(number), step) : openTicket(Number(number));
}

window.addEventListener("hashchange", route);

// --- Azioni ------------------------------------------------------------------------

$("check").onclick = check;
$("answer").onkeydown = (event) => { if (event.key === "Enter") check(); };
$("next-hint").onclick = () => {
  hintsShown += 1;
  renderHints();
};
$("reconnect").onclick = connect;
$("tutor-form").onsubmit = askTutor;
$("fixer-start").onclick = startFixer;
// Invio manda la domanda, Maiusc+Invio va a capo.
$("tutor-question").onkeydown = (event) => {
  if (event.key === "Enter" && !event.shiftKey) $("tutor-form").requestSubmit();
};
$("exercise-view").onclick = (event) => {
  const button = event.target.closest("button[data-command]");
  if (button) runInTerminal(button.dataset.command);
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
    [lessons, tickets, current] = await Promise.all([api("/api/lessons"), api("/api/scenarios"), api("/api/active")]);
    if (current) connect(); // pagina ricaricata con un ticket o un esercizio già avviato
  } catch (error) {
    showError(`Server non raggiungibile: ${error.message}`);
  }
  route();
})();
