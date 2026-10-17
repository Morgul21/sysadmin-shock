"""Backend della sandbox: dove vengono eseguiti davvero i comandi.

Il server MCP non sa se sta parlando con Docker o con un mock: vede solo un
`Sandbox` con `exec()`. Si sceglie con la variabile BREAKFIX_SANDBOX (docker | mock).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field


CONTAINER_NAME = os.getenv("BREAKFIX_CONTAINER", "breakfix-sandbox")
IMAGE_NAME = "breakfix-sandbox:latest"
SANDBOX_DIR = Path(__file__).resolve().parents[2] / "sandbox"

EXEC_TIMEOUT_SECONDS = 15
MAX_OUTPUT_CHARS = 4000

# Limiti del container: niente rete, memoria e processi limitati, niente escalation.
RUN_FLAGS = [
    "--network", "none",
    "--memory", "256m",
    "--memory-swap", "256m",
    "--pids-limit", "128",
    "--security-opt", "no-new-privileges",
    "--hostname", "sandbox",
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
        try:
            proc = subprocess.run(
                ["docker", "exec", self.container, "sh", "-c", command],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return ExecResult(
                exit_code=124,
                stdout="",
                stderr=f"timeout: comando interrotto dopo {self.timeout}s",
                truncated=False,
            )
        stdout, cut_out = _clip(proc.stdout)
        stderr, cut_err = _clip(proc.stderr)
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


# --- CLI per gestire il container ----------------------------------------------


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], text=True, check=check)


def up() -> None:
    _docker("build", "-t", IMAGE_NAME, str(SANDBOX_DIR))
    _docker("rm", "-f", CONTAINER_NAME, check=False)
    _docker("run", "-d", "--name", CONTAINER_NAME, *RUN_FLAGS, IMAGE_NAME)
    print(f"Sandbox pronta: {CONTAINER_NAME}")


def down() -> None:
    _docker("rm", "-f", CONTAINER_NAME, check=False)


def shell() -> None:
    """Shell interattiva nella sandbox: è da qui che chi si esercita diagnostica e ripara."""
    result = _docker("exec", "-it", "--workdir", "/root", CONTAINER_NAME, "bash", "-l", check=False)
    sys.exit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(prog="breakfix-sandbox", description="Gestisce il container sandbox")
    parser.add_argument("action", choices=["up", "down", "shell", "exec"])
    parser.add_argument("command", nargs="?", help="Comando da eseguire con 'exec'")
    args = parser.parse_args()

    if args.action == "up":
        up()
    elif args.action == "down":
        down()
    elif args.action == "shell":
        shell()
    else:
        if not args.command:
            parser.error("'exec' richiede un comando")
        result = get_sandbox().exec(args.command)
        print(result.model_dump_json(indent=2))
        sys.exit(0 if result.exit_code == 0 else 1)


if __name__ == "__main__":
    main()
