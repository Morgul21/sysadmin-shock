"""La UI dell'esercizio (FastAPI + xterm.js): ticket, terminale vero, indizi e verdetto in una pagina.

Fa quello che fa la CLI `breakfix-sandbox` (list, start, lessons, learn, shell, check), dal browser:
- l'API REST elenca i ticket e le lezioni delle basi, avvia uno scenario o un esercizio e dà il
  verdetto di check.sh (con la risposta, per gli esercizi che la chiedono);
- il terminale è una bash con TTY vero nella sandbox (Docker API: exec con tty), collegata
  al browser da un websocket: Tab, frecce, vim, top e less funzionano come in `breakfix-sandbox shell`.

Come nella shell della CLI, chi si esercita è root e i comandi non passano dal guardrail:
il guardrail protegge dagli agenti, non da chi si esercita. Il verdetto lo dà sempre check.sh.

Il pulsante "Fallo risolvere all'AI" lancia sul ticket attivo la stessa prova di `breakfix-eval`
(sandbox rotta da capo -> fixer -> check.sh), e la pagina ne segue i comandi mentre lavora.

Una shell di root nella sandbox non va esposta: il server ascolta solo su 127.0.0.1, e le
richieste che cambiano stato (POST, websocket) devono venire dalla pagina stessa (Origin):
un altro sito aperto nel browser non può avviare scenari né aprire il terminale.

Si avvia con `breakfix-ui`.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import secrets
import subprocess
import threading
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import docker
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers

from pydantic import BaseModel, Field

from breakfix import lessons, sandbox, tutor
from breakfix.agent import AgentRunError, build_llm_client, utf8_console
from breakfix.evaluate import evaluate_scenario
from breakfix.guardrail import BLOCKED_PREFIX
from breakfix.lab import DockerLab, Scenario, get_scenario, load_scenarios, scenario_number, tickets_for
from breakfix.lessons import Exercise, LessonLab


DEFAULT_PORT = 8000
STATIC_DIR = Path(__file__).resolve().parent / "static"
DOCKER_ERRORS = (RuntimeError, subprocess.CalledProcessError, FileNotFoundError, docker.errors.DockerException)
SESSION_VAR = "BREAKFIX_TERMINAL"
# Chiude i processi della sessione. La bash (il suo genitore è fuori dal container: ppid 0) per
# ultima: raccoglie i figli che muoiono, altrimenti resterebbero zombie del PID 1 (`sleep infinity`).
HANGUP = """
for pid in $(grep -lz '^{var}={token}$' /proc/[0-9]*/environ 2>/dev/null | cut -d/ -f3); do
    if [ "$(cut -d' ' -f4 /proc/$pid/stat)" = 0 ]; then shell=$pid; else kill -HUP $pid; fi
done
sleep 0.2
[ -z "$shell" ] || kill -HUP $shell
"""


class TerminalSession:
    """Una bash di root con TTY vero nella sandbox, come `breakfix-sandbox shell`, ma via Docker API.

    Con il TTY lo stream non è multiplexato: dal socket arrivano i byte del terminale così come sono.
    """

    def __init__(self, cols: int, rows: int) -> None:
        self.api = docker.from_env().api
        # Segna i processi della sessione (bash e quello che lancia): servono a chiuderli in close().
        self.token = secrets.token_hex(8)
        self.exec_id = self.api.exec_create(
            sandbox.CONTAINER_NAME, ["bash", "-l"], stdin=True, tty=True, workdir="/root",
            environment={"TERM": "xterm-256color", SESSION_VAR: self.token},
        )["Id"]
        sock = self.api.exec_start(self.exec_id, socket=True, tty=True)
        # Linux/macOS: un SocketIO attorno al socket; Windows: direttamente la NpipeSocket.
        self.sock = getattr(sock, "_sock", sock)
        # Con socket=True docker-py lascia al socket il timeout del client (60 s): un terminale fermo
        # (nessun output, es. mentre si legge il ticket) farebbe scadere la recv e chiudere la sessione.
        self.sock.settimeout(None)
        self.resize(cols, rows)

    def read(self) -> bytes:
        try:
            return self.sock.recv(4096)
        except OSError:  # su Windows la fine della sessione arriva come errore della pipe
            return b""

    def write(self, data: bytes) -> None:
        self.sock.sendall(data)

    def resize(self, cols: int, rows: int) -> None:
        with contextlib.suppress(docker.errors.APIError):  # la bash potrebbe essere già uscita
            self.api.exec_resize(self.exec_id, height=rows, width=cols)

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self.sock.close()
        # Docker non chiude la bash quando il terminale si stacca: senza questo, ogni pagina chiusa
        # lascerebbe processi nella sandbox (limite di 128). SIGHUP, come quando si chiude un terminale.
        hangup = HANGUP.format(var=SESSION_VAR, token=self.token)
        with contextlib.suppress(docker.errors.DockerException):
            self.api.exec_start(self.api.exec_create(sandbox.CONTAINER_NAME, ["sh", "-c", hangup])["Id"])


def scenario_view(scenario: Scenario) -> dict[str, Any]:
    """Quello che la pagina mostra di uno scenario: id e titolo no, direbbero la causa."""
    ticket = scenario.ticket
    return {
        "kind": "ticket",
        "number": scenario_number(scenario),
        "category": scenario.category,
        "difficulty": scenario.difficulty,
        "ticket": {"sender": ticket.sender, "subject": ticket.subject, "body": ticket.body.strip(),
                   "program": ticket.program, "user": ticket.user},
        # Tutti, ma la pagina li svela uno per volta: chi si esercita non bara con se stesso.
        "hints": list(scenario.hints),
        "man": list(scenario.man),
        # Le lezioni delle basi che preparano a questo ticket.
        "lessons": [{"number": n, "title": lessons.get_lesson(n).title} for n in scenario.lessons],
    }


def exercise_view(exercise: Exercise) -> dict[str, Any]:
    """Un esercizio con la sua lezione: qui niente da nascondere, tranne la soluzione."""
    lesson = lessons.get_lesson(exercise.lesson_number)
    keys = [e.key for e in lesson.exercises]
    position = keys.index(exercise.key)
    return {
        "kind": "esercizio",
        "key": exercise.key,
        "title": exercise.title,
        "type": exercise.kind,
        "task": exercise.task,
        "hints": list(exercise.hints),
        "next": keys[position + 1] if position + 1 < len(keys) else None,
        "lesson": {"number": lesson.number, "title": lesson.title, "track": lesson.track,
                   "man": list(lesson.man), "explanation": lesson.explanation,
                   "exercises": len(keys), "tickets": tickets_for(lesson)},
    }


class CheckRequest(BaseModel):
    # Solo per gli esercizi di tipo risposta; i ticket e gli esercizi di stato non la usano.
    answer: str | None = Field(default=None, max_length=lessons.MAX_ANSWER_CHARS)


class TutorRequest(BaseModel):
    question: str = Field(min_length=1, max_length=tutor.MAX_QUESTION_CHARS)
    # Gli indizi già aperti nella pagina: il tutor non va oltre il prossimo.
    hints_shown: int = Field(default=0, ge=0, le=20)


def same_origin(headers: Headers) -> bool:
    # Senza Origin è un client non browser (curl, i test): solo i browser possono essere ingannati.
    origin = headers.get("origin")
    return origin is None or origin == f"http://{headers.get('host')}"


def require_same_origin(request: Request) -> None:
    if not same_origin(request.headers):
        raise HTTPException(403, "richiesta da un'altra origine")


def _active() -> Scenario | None:
    scenario_id = sandbox.active_scenario()
    try:
        return get_scenario(scenario_id) if scenario_id else None
    except KeyError:  # etichetta di uno scenario che non esiste più
        return None


# --- "Fallo risolvere all'AI": il fixer sul ticket attivo, seguito dalla pagina ---------------

MAX_STEP_OUTPUT = 2000  # caratteri di output per comando mostrati nella pagina (l'audit ha tutto)


def fixer_step(arguments: dict[str, Any], result: str) -> dict[str, Any]:
    """Una chiamata del fixer a exec_in_sandbox, come la mostra la pagina."""
    step: dict[str, Any] = {"command": str(arguments.get("command", "")), "blocked": False, "exit_code": None}
    try:
        data = json.loads(result)
    except ValueError:
        return {**step, "output": result[-MAX_STEP_OUTPUT:]}
    if data.get("isError"):  # il guardrail, o un comando che il tool rifiuta
        text = "\n".join(str(c.get("text", "")) for c in data.get("content") or [])
        return {**step, "blocked": BLOCKED_PREFIX in text, "output": text[-MAX_STEP_OUTPUT:]}
    out = data.get("structuredContent") or {}
    output = (str(out.get("stdout", "")) + str(out.get("stderr", ""))).strip()
    return {**step, "exit_code": out.get("exit_code"), "output": output[-MAX_STEP_OUTPUT:]}


@dataclass
class FixerRun:
    scenario: str
    status: str = "running"  # running, done (c'è il verdetto), error (non è arrivato al verdetto)
    steps: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    task: asyncio.Task | None = None

    def view(self) -> dict[str, Any]:
        return {"status": self.status, "steps": self.steps, "result": self.result, "error": self.error}


# Una sola esecuzione per volta: c'è una sola sandbox.
_fixer: FixerRun | None = None


def _fixer_running() -> bool:
    return _fixer is not None and _fixer.status == "running"


def require_no_fixer() -> None:
    if _fixer_running():
        raise HTTPException(409, "l'AI sta lavorando sulla sandbox: aspetta che finisca")


async def _run_fixer(run: FixerRun, scenario: Scenario, client: Any) -> None:
    try:
        row = await evaluate_scenario(scenario, client, DockerLab(),
                                      on_tool=lambda arguments, result: run.steps.append(fixer_step(arguments, result)))
    except Exception as exc:  # es. Docker giù: senza sandbox non c'è nemmeno il verdetto
        run.status, run.error = "error", f"{type(exc).__name__}: {exc}"
        return
    run.result = {
        "passed": row.passed,
        "check_output": row.check_output,
        "answer": row.answer,
        "error": row.error,  # il fixer si è fermato a metà (es. modello non raggiungibile): il check vale comunque
        "tool_calls": row.tool_calls,
        "blocked_by_guardrail": row.blocked_by_guardrail,
        "llm_calls": row.llm_calls,
        "tokens": row.tokens,
        "duration_s": row.duration_s,
        "audit": Path(row.audit_path).name,
    }
    run.status = "done"


app = FastAPI(title="Sysadmin Shock")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def no_stale_page(request: Request, call_next):
    """Senza, il browser può tenere un app.js vecchio con un index.html nuovo (o il contrario) e la
    pagina si rompe. no-cache lo obbliga a ricontrollare: con l'ETag, se il file non è cambiato, 304."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/scenarios")
def scenarios() -> list[dict[str, Any]]:
    # Come `breakfix-sandbox list`: numero, categoria, difficoltà, oggetto; più le lezioni che preparano.
    return [{"number": number, "subject": s.ticket.subject, "category": s.category, "difficulty": s.difficulty,
             "lessons": list(s.lessons)}
            for number, s in enumerate(load_scenarios(), start=1)]


@app.get("/api/lessons")
def lesson_list() -> list[dict[str, Any]]:
    # Come `breakfix-sandbox lessons`: la roadmap delle basi, con i ticket a cui prepara ogni lezione.
    return [{"number": lesson.number, "title": lesson.title, "track": lesson.track,
             "man": list(lesson.man), "tickets": tickets_for(lesson),
             "exercises": [{"key": e.key, "title": e.title, "type": e.kind} for e in lesson.exercises]}
            for lesson in lessons.load_lessons()]


@app.get("/api/active")
def active() -> dict[str, Any] | None:
    if exercise := lessons.active_exercise():
        return exercise_view(exercise)
    scenario = _active()
    return scenario_view(scenario) if scenario else None


# Le funzioni qui sotto che aspettano Docker sono `def` normali: FastAPI le esegue in un thread,
# così mentre aspettano il server continua a servire il terminale.


def _start_sandbox(find: Callable[[str], Any], key: str, start: Callable[[Any], None]) -> Any:
    """Sandbox nuova per un ticket o un esercizio: 404 se non esiste, 503 se Docker non risponde."""
    global _fixer
    try:
        item = find(key)
    except KeyError as exc:
        raise HTTPException(404, exc.args[0]) from exc
    try:
        start(item)
    except DOCKER_ERRORS as exc:
        raise HTTPException(503, f"avvio fallito: {exc}. Docker Desktop è avviato? "
                                 "L'immagine va buildata una volta con `breakfix-sandbox up`.") from exc
    _fixer = None  # sandbox nuova: quello che ha fatto l'AI su quella vecchia non vale più
    return item


@app.post("/api/start/{number}", dependencies=[Depends(require_same_origin), Depends(require_no_fixer)])
def start(number: int) -> dict[str, Any]:
    return scenario_view(_start_sandbox(get_scenario, str(number), DockerLab().start))


@app.post("/api/learn/{key}", dependencies=[Depends(require_same_origin), Depends(require_no_fixer)])
def learn(key: str) -> dict[str, Any]:
    return exercise_view(_start_sandbox(lessons.get_exercise, key, LessonLab().start))


@app.post("/api/check", dependencies=[Depends(require_same_origin)])
def check(request: CheckRequest | None = None) -> dict[str, Any]:
    if exercise := lessons.active_exercise():
        result = LessonLab().check(exercise, request.answer if request else None)
    elif scenario := _active():
        result = DockerLab().check(scenario)
    else:
        raise HTTPException(409, "nessun ticket o esercizio attivo")
    return {"passed": result.passed, "output": result.output}


@app.get("/api/tutor")
def tutor_conversation() -> list[dict[str, Any]]:
    """La conversazione con il tutor sulla sandbox attiva (vuota con un ticket nuovo)."""
    return tutor.load_conversation(sandbox.container_id()).transcript


def _llm_client(who: str) -> Any:
    try:
        return build_llm_client()
    except SystemExit as exc:  # build_llm_client è pensata per la CLI: esce con il messaggio
        raise HTTPException(503, f"{who} non configurato: {exc.code}") from exc


@app.post("/api/tutor", dependencies=[Depends(require_same_origin)])
async def ask_tutor(request: TutorRequest) -> dict[str, Any]:
    # Solo i ticket: negli esercizi delle basi la risposta va trovata sul sistema, non chiesta.
    scenario = await asyncio.to_thread(_active)
    if scenario is None:
        raise HTTPException(409, "il tutor segue i ticket: avviane uno dalle Challenge")
    container = await asyncio.to_thread(sandbox.container_id)
    conversation = tutor.load_conversation(container)
    commands = await asyncio.to_thread(tutor.recent_commands)
    client = _llm_client("tutor")
    try:
        reply = await tutor.ask(scenario, request.question, client, conversation.memory,
                                commands=commands, hints_shown=request.hints_shown)
    except ValueError as exc:  # domanda fatta solo di spazi
        raise HTTPException(422, str(exc)) from exc
    except AgentRunError as exc:
        raise HTTPException(503, f"il tutor non ha risposto ({exc}). È avviato Ollama, o c'è la API key?") from exc
    conversation.add(request.question, reply)
    tutor.save_conversation(conversation)
    return conversation.transcript[-1]


@app.get("/api/fixer")
async def fixer_status() -> dict[str, Any] | None:
    """L'esecuzione del fixer sul ticket attivo: la pagina la interroga finché è in corso."""
    run = _fixer
    if run is None:
        return None
    if run.status != "running":  # finita: vale solo per il ticket su cui è stata fatta
        scenario = await asyncio.to_thread(_active)
        if scenario is None or scenario.id != run.scenario:
            return None
    return run.view()


@app.post("/api/fixer", status_code=202, dependencies=[Depends(require_same_origin), Depends(require_no_fixer)])
async def start_fixer() -> dict[str, Any]:
    """Come `breakfix-eval` sul ticket attivo: sandbox rotta da capo, fixer, check.sh. In sottofondo:
    la risposta arriva subito, i comandi e il verdetto con GET /api/fixer."""
    global _fixer
    scenario = await asyncio.to_thread(_active)
    if scenario is None:
        raise HTTPException(409, "l'AI ripara i ticket: avviane uno dalle Challenge")
    client = _llm_client("modello")
    run = FixerRun(scenario=scenario.id)
    run.task = asyncio.create_task(_run_fixer(run, scenario, client))  # il riferimento la tiene viva
    _fixer = run
    return run.view()


@app.websocket("/ws/terminal")
async def terminal(ws: WebSocket, cols: int = 80, rows: int = 24) -> None:
    """Dal browser arrivano messaggi JSON ({"input": testo} o {"resize": [colonne, righe]}),
    verso il browser i byte del terminale."""
    if not same_origin(ws.headers):
        await ws.close(code=1008)
        return
    await ws.accept()
    try:
        session = await asyncio.to_thread(TerminalSession, cols, rows)
    except DOCKER_ERRORS as exc:
        await ws.send_text(f"\r\nSandbox non raggiungibile: {exc}\r\n")
        await ws.close()
        return

    async def output() -> None:
        while data := await asyncio.to_thread(session.read):
            await ws.send_bytes(data)

    async def input_() -> None:
        while True:
            message = await ws.receive_json()
            if "input" in message:
                await asyncio.to_thread(session.write, str(message["input"]).encode("utf-8"))
            elif "resize" in message:
                new_cols, new_rows = message["resize"]
                await asyncio.to_thread(session.resize, int(new_cols), int(new_rows))

    # Finisce la prima delle due: la bash esce (exit) o il browser chiude la pagina.
    tasks = [asyncio.create_task(output()), asyncio.create_task(input_())]
    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    await asyncio.to_thread(session.close)  # sblocca anche la read in corso nel thread
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    with contextlib.suppress(RuntimeError, WebSocketDisconnect):
        await ws.close()


def main() -> None:
    import uvicorn

    utf8_console()  # il log dell'agente stampa le risposte del modello (es. "→"): su Windows senza, l'esecuzione fallisce
    load_dotenv()  # provider e modello del tutor e del fixer
    parser = argparse.ArgumentParser(prog="breakfix-ui", description="La UI dell'esercizio nel browser")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true", help="non aprire il browser")
    args = parser.parse_args()
    # Solo 127.0.0.1: la UI dà una shell di root nella sandbox. In un container serve 0.0.0.0
    # (BREAKFIX_UI_HOST), e a limitare l'accesso al solo PC è la porta pubblicata su 127.0.0.1 (compose.yaml).
    host = os.getenv("BREAKFIX_UI_HOST") or "127.0.0.1"
    # 0.0.0.0 non si apre nel browser: dal PC la UI si raggiunge su localhost.
    url = f"http://{'localhost' if host == '0.0.0.0' else host}:{args.port}"
    print(f"Sysadmin Shock su {url} (Ctrl+C per fermare)")
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, (url,)).start()
    uvicorn.run(app, host=host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
