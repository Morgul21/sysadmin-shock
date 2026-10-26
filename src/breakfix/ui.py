"""La UI dell'esercizio (Streamlit): ticket, terminale, indizi e verdetto nella stessa pagina.

Fa quello che fa la CLI `breakfix-sandbox` (list, start, shell, check), dal browser:
- a sinistra si sceglie il ticket e si avvia lo scenario;
- nella sezione dell'esercizio c'è il ticket, i comandi per orientarsi (eseguibili con un clic),
  gli indizi graduali e il pulsante del check;
- il terminale è una casella di comando: ogni comando è un `docker exec` (bash, timeout 15 s),
  quindi niente programmi a tutto schermo (vim, top, less), ma la `cd` viene ricordata;
- "Esplora file" sfoglia la sandbox senza ricordare i percorsi: niente Tab nel browser.

Come nella shell della CLI, chi si esercita è root e i comandi non passano dal guardrail:
il guardrail protegge dagli agenti, non da chi si esercita. Il verdetto lo dà sempre check.sh.

Si avvia con `breakfix-ui`.
"""

from __future__ import annotations

import posixpath
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import streamlit as st

from breakfix import sandbox
from breakfix.lab import DockerLab, Scenario, get_scenario, load_scenarios, scenario_number
from breakfix.sandbox import DockerSandbox, Sandbox


HOME = "/root"
# Dopo ogni comando la directory corrente: è così che la `cd` sopravvive tra due docker exec.
CWD_MARKER = "__breakfix_cwd__="
DOCKER_ERRORS = (RuntimeError, subprocess.CalledProcessError, FileNotFoundError)
MAX_FILE_BYTES = 20000
# Il metodo di un sistemista, uguale per tutti i ticket: non dice la causa, dice da dove partire.
FIRST_STEPS = (
    ("Riproduci il problema", "gestionale"),
    ("Dove sta il comando", "which gestionale"),
    ("Cosa avvia e con quale utente", 'cat "$(which gestionale)"'),
    ("Le unità dei servizi (dicono dove va il log)", "ls -l /etc/systemd/system/"),
    ("Processi per memoria occupata", "ps aux --sort=-rss | head"),
    ("Limite di memoria del container", "cat /sys/fs/cgroup/memory.max"),
)
TOOLBOX = (
    "**Log:** `tail -n 20 <file>` · **Permessi:** `ls -l`, `stat`, `namei -l <percorso>`, `getfacl <file>`"
    "  \n**Memoria:** `free -m`, `df -h`, `cat /sys/fs/cgroup/memory.stat`"
)


@dataclass(frozen=True)
class CommandRun:
    cwd: str
    command: str
    output: str
    exit_code: int

    def __str__(self) -> str:
        status = f"[exit {self.exit_code}]" if self.exit_code else ""
        return "\n".join(line for line in (f"root@sandbox:{self.cwd}# {self.command}", self.output, status) if line)


@dataclass(frozen=True)
class Entry:
    name: str
    is_dir: bool


def scenario_label(scenario: Scenario) -> str:
    # Come `breakfix-sandbox list`: id e titolo direbbero la causa.
    return f"{scenario.ticket.subject} ({scenario.category}, {scenario.difficulty})"


def run_command(box: Sandbox, command: str, cwd: str) -> tuple[CommandRun, str]:
    """Esegue un comando nella directory `cwd`; restituisce l'esito e la nuova directory corrente."""
    script = f'cd {shlex.quote(cwd)} 2>/dev/null\n{command}\nrc=$?; printf "\\n{CWD_MARKER}%s" "$PWD"; exit $rc'
    result = box.exec(f"bash -c {shlex.quote(script)}")
    stdout, marker, new_cwd = result.stdout.rpartition(CWD_MARKER)
    if not marker:  # timeout, o il comando ha chiamato exit
        stdout, new_cwd = result.stdout, cwd
    output = "\n".join(part for part in (stdout.rstrip("\n"), result.stderr.rstrip("\n")) if part)
    if result.truncated:
        output = f"[output troncato: ultimi {sandbox.MAX_OUTPUT_CHARS} caratteri]\n{output}"
    return CommandRun(cwd, command, output, result.exit_code), new_cwd.strip() or cwd


def list_dir(box: Sandbox, path: str) -> tuple[str, list[Entry]]:
    """`ls -la` della directory (com'è, con il + delle ACL) e le voci in cui si può entrare o che si possono aprire."""
    quoted = shlex.quote(path)
    listing = box.exec(f"ls -la {quoted}")
    if listing.exit_code != 0:
        return (listing.stdout + listing.stderr).strip(), []
    # %Y: il tipo del file a cui punta un link, così un link a una directory si apre come directory.
    found = box.exec(f"find {quoted} -mindepth 1 -maxdepth 1 -printf '%Y %f\\n'")
    entries = []
    for line in found.stdout.splitlines():
        kind, _, name = line.partition(" ")
        if kind in ("d", "f"):
            entries.append(Entry(name, kind == "d"))
    entries.sort(key=lambda e: (not e.is_dir, e.name))
    return listing.stdout.strip(), entries


def read_file(box: Sandbox, path: str) -> str:
    quoted = shlex.quote(path)
    result = box.exec(f"if [ -s {quoted} ] && ! grep -Iq . {quoted}; then echo '[file binario]'; "
                      f"else head -c {MAX_FILE_BYTES} {quoted}; fi")
    return (result.stdout + result.stderr).rstrip("\n")


# --- Pagina ------------------------------------------------------------------------


def _reset_state(scenario_id: str | None) -> None:
    st.session_state.update(scenario=scenario_id, cwd=HOME, history=[], hints=0, verdict=None,
                            browse=HOME, opened=None)


def _execute(command: str) -> None:
    run, st.session_state.cwd = run_command(DockerSandbox(), command, st.session_state.cwd)
    st.session_state.history.append(run)


def _step(command: str) -> None:
    _execute(command)
    st.session_state.tab = "Terminale"  # per vedere l'output anche se era aperta l'esplora file


def _browse(path: str) -> None:
    # Relativo alla directory che si sta guardando, come una `cd`.
    st.session_state.update(browse=posixpath.normpath(posixpath.join(st.session_state.browse, path)), opened=None)


def _sidebar(scenarios: list[Scenario], active: Scenario | None) -> None:
    st.sidebar.title("Sysadmin Shock")
    st.sidebar.caption("Scegli un ticket: la sandbox riparte sana e viene rotta come dice lo scenario.")
    index = scenarios.index(active) if active in scenarios else 0
    chosen = st.sidebar.selectbox("Ticket", scenarios, index=index,
                                  format_func=lambda s: f"{scenario_number(s)}. {scenario_label(s)}")
    if st.sidebar.button("Avvia", type="primary", width="stretch"):
        with st.spinner("Preparo la sandbox..."):
            try:
                DockerLab().start(chosen)
            except DOCKER_ERRORS as exc:
                st.sidebar.error(f"Avvio fallito: {exc}\n\nDocker Desktop è avviato? "
                                 "L'immagine va buildata una volta con `breakfix-sandbox up`.")
                return
        _reset_state(chosen.id)


def _exercise(scenario: Scenario) -> None:
    ticket = scenario.ticket
    st.subheader(f"Ticket n. {scenario_number(scenario)}")
    st.caption(f"{scenario.category} · {scenario.difficulty}")
    with st.container(border=True):
        st.markdown(f"**Da:** {ticket.sender}  \n**Oggetto:** {ticket.subject}")
        st.text(ticket.body.strip())
        st.caption(f"[Helpdesk] Programma: {ticket.program} (si avvia con il comando `{ticket.program}`)  \n"
                   f"[Helpdesk] Utente con cui gira: {ticket.user}")

    with st.expander("Come orientarsi"):
        st.caption("I primi passi di ogni ticket: un clic esegue il comando nel terminale.")
        for label, command in FIRST_STEPS:
            st.button(f"`{command}`", help=label, key=f"step-{command}", on_click=_step, args=(command,))
        st.markdown(TOOLBOX)

    shown = st.session_state.hints
    total = len(scenario.hints)
    for number, hint in enumerate(scenario.hints[:shown], start=1):
        st.info(f"**Indizio {number}/{total}.** {hint}")
    if shown < total:
        if st.button(f"Mostra indizio {shown + 1}/{total}"):
            st.session_state.hints += 1
            st.rerun()
    else:
        st.caption("Man page utili: " + ", ".join(scenario.man))

    if st.button("Verifica", type="primary"):
        with st.spinner("Eseguo il check..."):
            st.session_state.verdict = DockerLab().check(scenario)
        if st.session_state.verdict.passed:
            st.balloons()
    if verdict := st.session_state.verdict:
        (st.success if verdict.passed else st.error)("PASS: riparato" if verdict.passed else "FAIL: non ancora")
        st.code(verdict.output, language=None)


def _terminal() -> None:
    history = st.container(height=520)
    command = st.chat_input(f"root@sandbox:{st.session_state.cwd}#  scrivi un comando e premi Invio")
    if command:
        with st.spinner(command):
            _execute(command)
    with history:
        if not st.session_state.history:
            st.caption("Come in `breakfix-sandbox shell`: sei root sul server. "
                       "Non sai da dove partire? Apri \"Come orientarsi\" a sinistra.")
        for run in st.session_state.history:
            st.code(str(run), language=None, wrap_lines=True)


def _explorer() -> None:
    path = st.session_state.browse
    jump = st.text_input("Percorso", value=path, key=f"jump-{path}")
    if jump != path:
        _browse(jump)
        st.rerun()
    up, here = st.columns(2)
    up.button("Su di un livello", on_click=_browse, args=(posixpath.dirname(path.rstrip("/")) or "/",),
              disabled=path == "/", width="stretch")
    here.button("Usa nel terminale", help="cd del terminale in questa directory", width="stretch",
                on_click=lambda: st.session_state.update(cwd=path))

    listing, entries = list_dir(DockerSandbox(), path)
    st.code(listing, language=None)
    if entries:
        names = [f"{e.name}/" if e.is_dir else e.name for e in entries]
        choice = st.selectbox("Apri", names, index=None, placeholder="una directory o un file",
                              key=f"open-{path}")
        if choice:
            target = posixpath.join(path, choice.rstrip("/"))
            if choice.endswith("/"):
                _browse(target)
                st.rerun()
            st.session_state.opened = target
    if opened := st.session_state.opened:
        st.markdown(f"**{opened}**")
        st.code(read_file(DockerSandbox(), opened), language=None, wrap_lines=True)


def app() -> None:
    st.set_page_config(page_title="Sysadmin Shock", layout="wide")
    scenarios = load_scenarios()
    try:
        active_id = sandbox.active_scenario()
    except FileNotFoundError:
        st.error("Docker non trovato: installa e avvia Docker Desktop.")
        return
    active = get_scenario(active_id) if active_id else None
    _sidebar(scenarios, active)
    if st.session_state.get("scenario") is None and active:
        _reset_state(active.id)  # pagina ricaricata con uno scenario già avviato
    if not st.session_state.get("scenario"):
        st.info("Scegli un ticket nella barra a sinistra e premi **Avvia**.")
        return
    left, right = st.columns([2, 3], gap="large")
    with left:
        _exercise(get_scenario(st.session_state.scenario))
    with right:
        # Solo la scheda aperta gira: l'esplora file non rifà ls e find a ogni comando del terminale.
        terminal, files = st.tabs(["Terminale", "Esplora file"], key="tab", on_change="rerun")
        if terminal.open:
            with terminal:
                _terminal()
        if files.open:
            with files:
                _explorer()


def main() -> None:
    from streamlit.web import cli

    sys.argv = ["streamlit", "run", str(Path(__file__)), "--browser.gatherUsageStats", "false", *sys.argv[1:]]
    sys.exit(cli.main())


if __name__ == "__main__":
    app()
