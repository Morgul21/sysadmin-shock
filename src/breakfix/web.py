"""La UI dell'esercizio (FastAPI + xterm.js): ticket, terminale vero, indizi e verdetto in una pagina.

Fa quello che fa la CLI `breakfix-sandbox` (list, start, shell, check), dal browser:
- l'API REST elenca i ticket, avvia uno scenario e dà il verdetto di check.sh;
- il terminale è una bash con TTY vero nella sandbox (Docker API: exec con tty), collegata
  al browser da un websocket: Tab, frecce, vim, top e less funzionano come in `breakfix-sandbox shell`.

Come nella shell della CLI, chi si esercita è root e i comandi non passano dal guardrail:
il guardrail protegge dagli agenti, non da chi si esercita. Il verdetto lo dà sempre check.sh.

Una shell di root nella sandbox non va esposta: il server ascolta solo su 127.0.0.1, e le
richieste che cambiano stato (POST, websocket) devono venire dalla pagina stessa (Origin):
un altro sito aperto nel browser non può avviare scenari né aprire il terminale.

Si avvia con `breakfix-ui`.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import secrets
import subprocess
import threading
import webbrowser
from pathlib import Path
from typing import Any

import docker
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers

from breakfix import sandbox
from breakfix.lab import DockerLab, Scenario, get_scenario, load_scenarios, scenario_number


HOST = "127.0.0.1"
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
        "number": scenario_number(scenario),
        "category": scenario.category,
        "difficulty": scenario.difficulty,
        "ticket": {"sender": ticket.sender, "subject": ticket.subject, "body": ticket.body.strip(),
                   "program": ticket.program, "user": ticket.user},
        # Tutti, ma la pagina li svela uno per volta: chi si esercita non bara con se stesso.
        "hints": list(scenario.hints),
        "man": list(scenario.man),
    }


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


app = FastAPI(title="Sysadmin Shock")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/scenarios")
def scenarios() -> list[dict[str, Any]]:
    # Come `breakfix-sandbox list`: numero, categoria, difficoltà, oggetto.
    return [{"number": number, "subject": s.ticket.subject, "category": s.category, "difficulty": s.difficulty}
            for number, s in enumerate(load_scenarios(), start=1)]


@app.get("/api/active")
def active() -> dict[str, Any] | None:
    scenario = _active()
    return scenario_view(scenario) if scenario else None


@app.post("/api/start/{number}", dependencies=[Depends(require_same_origin)])
async def start(number: int) -> dict[str, Any]:
    try:
        scenario = get_scenario(str(number))
    except KeyError as exc:
        raise HTTPException(404, exc.args[0]) from exc
    try:
        await asyncio.to_thread(DockerLab().start, scenario)
    except DOCKER_ERRORS as exc:
        raise HTTPException(503, f"avvio fallito: {exc}. Docker Desktop è avviato? "
                                 "L'immagine va buildata una volta con `breakfix-sandbox up`.") from exc
    return scenario_view(scenario)


@app.post("/api/check", dependencies=[Depends(require_same_origin)])
async def check() -> dict[str, Any]:
    scenario = _active()
    if scenario is None:
        raise HTTPException(409, "nessuno scenario attivo")
    result = await asyncio.to_thread(DockerLab().check, scenario)
    return {"passed": result.passed, "output": result.output}


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

    parser = argparse.ArgumentParser(prog="breakfix-ui", description="La UI dell'esercizio nel browser")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true", help="non aprire il browser")
    args = parser.parse_args()
    url = f"http://{HOST}:{args.port}"
    print(f"Sysadmin Shock su {url} (Ctrl+C per fermare)")
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, (url,)).start()
    uvicorn.run(app, host=HOST, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
