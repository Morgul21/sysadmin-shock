// La pagina dell'esercizio: ticket e indizi da /api, terminale vero da /ws/terminal.

// Il metodo di un sistemista, uguale per tutti i ticket: non dice la causa, dice da dove partire.
const FIRST_STEPS = [
  ["Riproduci il problema", "gestionale"],
  ["Dove sta il comando", "which gestionale"],
  ["Cosa avvia e con quale utente", 'cat "$(which gestionale)"'],
  ["Le unità dei servizi (dicono dove va il log)", "ls -l /etc/systemd/system/"],
  ["Processi per memoria occupata", "ps aux --sort=-rss | head"],
  ["Limite di memoria del container", "cat /sys/fs/cgroup/memory.max"],
];

const $ = (id) => document.getElementById(id);
let scenario = null;
let hintsShown = 0;
let socket = null;

// --- API -------------------------------------------------------------------------

async function api(path, method = "GET") {
  const response = await fetch(path, { method });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || response.statusText);
  return body;
}

// --- Ticket e indizi ---------------------------------------------------------------

function escape(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// Gli indizi usano i backtick per i comandi, come il markdown.
function withCode(text) {
  return escape(text).replace(/`([^`]+)`/g, "<code>$1</code>");
}

function showError(message) {
  $("error").textContent = message;
  $("error").hidden = !message;
}

function render(view) {
  scenario = view;
  hintsShown = 0;
  $("empty").hidden = Boolean(view);
  $("active").hidden = !view;
  $("verdict").hidden = true;
  if (!view) return;
  const t = view.ticket;
  $("scenarios").value = String(view.number);
  $("ticket-number").textContent = `Ticket n. ${view.number}`;
  $("ticket-meta").textContent = `${view.category} · ${view.difficulty}`;
  $("ticket-sender").textContent = t.sender;
  $("ticket-subject").textContent = t.subject;
  $("ticket-body").textContent = t.body;
  $("ticket-helpdesk").innerHTML =
    `[Helpdesk] Programma: ${escape(t.program)} (si avvia con il comando <code>${escape(t.program)}</code>)<br>` +
    `[Helpdesk] Utente con cui gira: ${escape(t.user)}`;
  renderHints();
}

function renderHints() {
  const { hints, man } = scenario;
  $("hints").innerHTML = hints.slice(0, hintsShown)
    .map((hint, i) => `<p class="hint"><b>Indizio ${i + 1}/${hints.length}.</b> ${withCode(hint)}</p>`)
    .join("");
  const done = hintsShown >= hints.length;
  $("next-hint").hidden = done;
  $("next-hint").textContent = `Mostra indizio ${hintsShown + 1}/${hints.length}`;
  $("man").hidden = !done;
  $("man").textContent = `Man page utili: ${man.join(", ")}`;
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

$("start").onclick = async () => {
  $("start").disabled = true;
  $("busy").hidden = false;
  showError("");
  try {
    render(await api(`/api/start/${$("scenarios").value}`, "POST"));
    connect(); // il container è nuovo: la vecchia shell non esiste più
  } catch (error) {
    showError(error.message);
  } finally {
    $("start").disabled = false;
    $("busy").hidden = true;
  }
};

$("next-hint").onclick = () => {
  hintsShown += 1;
  renderHints();
};

$("check").onclick = async () => {
  $("check").disabled = true;
  try {
    const result = await api("/api/check", "POST");
    $("verdict-status").className = `verdict ${result.passed ? "pass" : "fail"}`;
    $("verdict-status").textContent = result.passed ? "PASS: riparato" : "FAIL: non ancora";
    $("verdict-output").textContent = result.output;
    $("verdict").hidden = false;
  } catch (error) {
    showError(error.message);
  } finally {
    $("check").disabled = false;
  }
};

$("reconnect").onclick = connect;

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
    const list = await api("/api/scenarios");
    $("scenarios").innerHTML = list
      .map((s) => `<option value="${s.number}">${s.number}. ${escape(s.subject)} (${s.category}, ${s.difficulty})</option>`)
      .join("");
    const active = await api("/api/active");
    render(active);
    if (active) connect(); // pagina ricaricata con uno scenario già avviato
    else term.write("Avvia un ticket: qui si apre la shell di root sul server.\r\n");
  } catch (error) {
    showError(`Server non raggiungibile: ${error.message}`);
  }
})();
