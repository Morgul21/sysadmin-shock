"""Guardrail di input su `exec_in_sandbox`: decide se un comando può essere eseguito.

Non è il confine di sicurezza (quello è il container: niente rete, limiti di memoria e
processi). È la policy che vieta a chi usa il tool le "riparazioni" che un sistemista non
farebbe mai (chmod 777, setuid) e i comandi che distruggono la sandbox invece di ripararla.
Sta nel server MCP, quindi vale per qualunque host: il nostro agente, Claude Desktop, ...

Una denylist si aggira costruendo il comando a runtime (eval, base64, `| sh`): per questo
blocchiamo anche quei costrutti, a costo di qualche falso positivo.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass


BLOCKED_PREFIX = "Comando bloccato dal guardrail"

# Directory su cui un'operazione ricorsiva (rm -r, chmod -R, chown -R) non ha mai senso come fix.
PROTECTED_DIRS = {
    "/", "/bin", "/boot", "/dev", "/etc", "/home", "/lib", "/lib64", "/opt", "/proc",
    "/root", "/sbin", "/srv", "/srv/app", "/sys", "/usr", "/var",
}
AUTH_FILES = ("/etc/shadow", "/etc/gshadow", "/etc/passwd", "/etc/group", "/etc/sudoers")

# Prefissi che non cambiano il comando vero e proprio: `sudo chmod ...` è un `chmod ...`.
WRAPPERS = {"sudo", "nohup", "exec", "command", "nice", "env", "time", "builtin"}

SEGMENT_SEPARATORS = re.compile(r"\$\(|[;&|\n()`]")
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


@dataclass(frozen=True)
class Blocked:
    rule: str
    reason: str

    def message(self) -> str:
        return f"{BLOCKED_PREFIX} [{self.rule}]: {self.reason}. Il comando non è stato eseguito."


# --- Regole sul comando intero ---------------------------------------------------

RAW_RULES = [
    (
        "comando-dinamico",
        re.compile(r"\beval\b|\bbase64\s+(-d|--decode)\b|\|\s*(ba|da)?sh\b|\b(ba|da)?sh\s+-c\b"
                   r"|\b(python3?|perl)\s+-[ce]\b"),
        "il comando viene costruito a runtime (eval, base64, | sh, -c): non è validabile",
    ),
    ("fork-bomb", re.compile(r":\s*\(\s*\)\s*\{"), "fork bomb"),
    (
        "file-di-autenticazione",
        re.compile(r"(>>?|\btee\b[^;&|]*|\bsed\s+-i[^;&|]*)\s*(" + "|".join(map(re.escape, AUTH_FILES)) + r")"),
        "modifica diretta di passwd/shadow/group/sudoers",
    ),
]


def _segments(command: str) -> list[list[str]]:
    """Spezza il comando in sotto-comandi (; && || | $( ) `) e ciascuno in token."""
    segments = []
    for part in SEGMENT_SEPARATORS.split(command):
        try:
            tokens = shlex.split(part)
        except ValueError:  # virgolette sbilanciate: meglio un'analisi grezza che nessuna
            tokens = part.split()
        while tokens and (tokens[0] in WRAPPERS or ASSIGNMENT.match(tokens[0])):
            tokens = tokens[1:]
        if tokens:
            tokens[0] = tokens[0].rsplit("/", 1)[-1]  # /bin/chmod -> chmod
            segments.append(tokens)
    return segments


def _is_recursive(args: list[str]) -> bool:
    return any(a == "--recursive" or (re.fullmatch(r"-[A-Za-z]+", a) and "r" in a.lower()) for a in args)


def _targets(args: list[str]) -> list[str]:
    # /srv/app/, /srv/app/* e /srv/app sono la stessa cosa per noi; "/*" diventa "/".
    return [re.sub(r"(/\*?)+$", "", a) or "/" for a in args if not a.startswith("-")]


def _check_chmod_mode(mode: str) -> Blocked | None:
    if re.fullmatch(r"[0-7]{1,4}", mode):
        bits = int(mode, 8)
        if bits & 0o6000:
            return Blocked("setuid", "bit setuid/setgid: è un'escalation di privilegi, non un fix")
        # 1777 (sticky + scrivibile da tutti) è il permesso corretto di /tmp: lo lasciamo passare.
        if bits & 0o002 and not bits & 0o1000:
            return Blocked("scrivibile-da-tutti", "permessi di scrittura a tutti (es. 777, o+w): correzione eccessiva")
        return None
    for clause in mode.split(","):
        match = re.fullmatch(r"([ugoa]*)([+=])([rwxXst]*)", clause)
        if not match:
            continue
        who, _, perms = match.groups()
        if "s" in perms:
            return Blocked("setuid", "bit setuid/setgid: è un'escalation di privilegi, non un fix")
        # senza destinatari (`chmod +w`) vale l'umask, quindi niente scrittura per "altri"
        if "w" in perms and ("o" in who or "a" in who) and "t" not in perms:
            return Blocked("scrivibile-da-tutti", "permessi di scrittura a tutti (es. 777, o+w): correzione eccessiva")
    return None


def _check_segment(tokens: list[str]) -> Blocked | None:
    cmd, args = tokens[0], tokens[1:]

    if cmd in {"chmod", "chown", "chgrp", "rm"}:
        if "--no-preserve-root" in args:
            return Blocked("ricorsivo-di-sistema", "--no-preserve-root")
        if _is_recursive(args) and PROTECTED_DIRS.intersection(_targets(args)):
            return Blocked("ricorsivo-di-sistema", f"{cmd} ricorsivo su una directory di sistema")

    if cmd == "chmod":
        modes = [a for a in args if not a.startswith("-") or re.fullmatch(r"-[rwxXst]+", a)]
        if modes:
            return _check_chmod_mode(modes[0])

    if cmd == "kill" and ("1" in args or "-1" in args):
        # PID 1 è il processo che tiene in vita il container; -1 = tutti i processi.
        # Falso positivo noto: `kill -1 <pid>` (SIGHUP) va scritto `kill -HUP <pid>`.
        return Blocked("distruzione-sandbox", "kill di PID 1 o di tutti i processi (-1)")
    if cmd in {"pkill", "killall"} and ("sleep" in args or "-1" in args):
        return Blocked("distruzione-sandbox", "termina il processo principale del container (sleep)")
    if cmd in {"shutdown", "reboot", "halt", "poweroff", "telinit"} or (cmd == "init" and args[:1] in (["0"], ["6"])):
        return Blocked("distruzione-sandbox", "spegne o riavvia il sistema")
    if cmd.startswith("mkfs") or (cmd == "dd" and any(a.startswith("of=/dev/") for a in args)):
        return Blocked("distruzione-sandbox", "scrive direttamente su un dispositivo")
    return None


def check_command(command: str) -> Blocked | None:
    """Restituisce il motivo del blocco, oppure None se il comando può essere eseguito."""
    for rule, pattern, reason in RAW_RULES:
        if pattern.search(command):
            return Blocked(rule, reason)
    for tokens in _segments(command):
        blocked = _check_segment(tokens)
        if blocked:
            return blocked
    return None
