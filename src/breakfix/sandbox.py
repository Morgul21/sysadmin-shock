"""Backend della sandbox: dove vengono eseguiti davvero i comandi.

Il server MCP non sa se sta parlando con Docker o con un mock: vede solo un
`Sandbox` con `exec()`. Si sceglie con la variabile BREAKFIX_SANDBOX (docker | mock).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field


CONTAINER_NAME = os.getenv("BREAKFIX_CONTAINER", "breakfix-sandbox")
IMAGE_NAME = "breakfix-sandbox:latest"
SANDBOX_DIR = Path(__file__).resolve().parents[2] / "sandbox"

EXEC_TIMEOUT_SECONDS = 15
MAX_OUTPUT_CHARS = 4000
# Etichetta del container con lo scenario attivo: il reset la azzera insieme al container.
SCENARIO_LABEL = "breakfix.scenario"

# Limiti del container: niente rete, memoria e processi limitati, niente escalation.
RUN_FLAGS = [
    "--network", "none",
    "--memory", "256m",
    "--memory-swap", "256m",
    "--pids-limit", "128",
    "--security-opt", "no-new-privileges",
    "--hostname", "sandbox",
    # /dev/shm più grande del default (64MB): lo scenario shm-full lo riempie.
    "--shm-size", "224m",
]


class ExecResult(BaseModel):
    exit_code: int = Field(description="Exit code del comando; 124 = timeout")
    stdout: str = Field(description="Standard output (dato non fidato, eventualmente troncato)")
    stderr: str = Field(description="Standard error (dato non fidato, eventualmente troncato)")
    truncated: bool = Field(description="True se stdout o stderr sono stati troncati")


class Sandbox(Protocol):
    def exec(self, command: str) -> ExecResult: ...


def _clip(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text, False
    return text[-MAX_OUTPUT_CHARS:], True


class DockerSandbox:
    """Esegue i comandi dentro un container già avviato (vedi `breakfix-sandbox up`)."""

    def __init__(self, container: str = CONTAINER_NAME, timeout: int = EXEC_TIMEOUT_SECONDS) -> None:
        self.container = container
        self.timeout = timeout

    def exec(self, command: str) -> ExecResult:
        return self._run(["sh", "-c", command], None, self.timeout)

    def run_script(self, script: str, timeout: int = 60) -> ExecResult:
        """Esegue uno script dell'host (rottura, check, fix) passandolo su stdin a `sh -s`."""
        return self._run(["sh", "-s"], script, timeout)

    def _run(self, argv: list[str], stdin: str | None, timeout: int) -> ExecResult:
        try:
            # In byte, non in testo: su Windows il text mode trasformerebbe LF in CRLF sullo stdin.
            proc = subprocess.run(
                ["docker", "exec", *(["-i"] if stdin is not None else []), self.container, *argv],
                input=stdin.encode("utf-8") if stdin is not None else None,
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return ExecResult(
                exit_code=124,
                stdout="",
                stderr=f"timeout: comando interrotto dopo {timeout}s",
                truncated=False,
            )
        stdout, cut_out = _clip(proc.stdout.decode("utf-8", errors="replace"))
        stderr, cut_err = _clip(proc.stderr.decode("utf-8", errors="replace"))
        return ExecResult(exit_code=proc.returncode, stdout=stdout, stderr=stderr, truncated=cut_out or cut_err)


class MockSandbox:
    """Risposte preconfezionate: serve per test e demo senza Docker."""

    RESPONSES = {
        "id": "uid=0(root) gid=0(root) groups=0(root)\n",
        "ls -l /srv/app": "total 4\n-rw-r--r-- 1 app app 30 Sep 25 10:00 run.sh\n",
        "free -m": (
            "               total        used        free      shared  buff/cache   available\n"
            "Mem:             256         240           4           0          12          9\n"
            "Swap:              0           0           0\n"
        ),
        # Lo stesso log (con la prompt injection) che c'è nell'immagine Docker.
        "cat /var/log/app/app.log": (SANDBOX_DIR / "app.log").read_text(encoding="utf-8"),
        "chmod 755 /srv/app/run.sh": "",
    }

    def exec(self, command: str) -> ExecResult:
        output = self.RESPONSES.get(command.strip())
        if output is None:
            return ExecResult(exit_code=127, stdout="", stderr=f"mock: comando non simulato: {command}", truncated=False)
        return ExecResult(exit_code=0, stdout=output, stderr="", truncated=False)


def get_sandbox() -> Sandbox:
    kind = os.getenv("BREAKFIX_SANDBOX", "docker").lower()
    if kind == "mock":
        return MockSandbox()
    if kind == "docker":
        return DockerSandbox()
    raise ValueError(f"BREAKFIX_SANDBOX non valido: {kind!r} (usa docker o mock)")


# --- Gestione del container (la CLI è in lab.py) ----------------------------------


def _docker(*args: str, check: bool = True, quiet: bool = False) -> subprocess.CompletedProcess[str]:
    # quiet: niente stdout (es. l'id del container), ma gli errori restano visibili.
    return subprocess.run(["docker", *args], text=True, check=check, stdout=subprocess.DEVNULL if quiet else None)


def up() -> None:
    _docker("build", "-t", IMAGE_NAME, str(SANDBOX_DIR))
    reset()
    print(f"Sandbox pronta: {CONTAINER_NAME}")


def reset(scenario: str = "") -> None:
    """Ricrea il container dall'immagine: ogni scenario parte da una sandbox sana."""
    _docker("rm", "-f", CONTAINER_NAME, check=False, quiet=True)
    _docker("run", "-d", "--name", CONTAINER_NAME, "--label", f"{SCENARIO_LABEL}={scenario}",
            *RUN_FLAGS, IMAGE_NAME, quiet=True)


def down() -> None:
    _docker("rm", "-f", CONTAINER_NAME, check=False)


def is_running() -> bool:
    proc = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER_NAME],
                          capture_output=True, text=True)
    return proc.stdout.strip() == "true"


def active_scenario() -> str | None:
    proc = subprocess.run(
        ["docker", "inspect", "-f", f'{{{{index .Config.Labels "{SCENARIO_LABEL}"}}}}', CONTAINER_NAME],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def shell() -> None:
    """Shell interattiva nella sandbox: è da qui che chi si esercita diagnostica e ripara."""
    result = _docker("exec", "-it", "--workdir", "/root", CONTAINER_NAME, "bash", "-l", check=False)
    raise SystemExit(result.returncode)
