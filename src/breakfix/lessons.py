"""Le basi: lezioni brevi con esercizi verificati, che preparano ai ticket.

Una lezione è una cartella in lessons/ il cui nome inizia con il suo numero nella roadmap
(es. 05-leggere-i-permessi), con:
- lesson.toml: titolo, percorso, man page e gli esercizi (testo, tipo, indizi);
- lesson.md: la spiegazione, in un markdown minimo (titoli ##, elenchi, blocchi ```); i blocchi
  ```prova sono comandi che la UI esegue nel terminale con un clic;
- una cartella per esercizio con setup.sh (prepara la sandbox, con dati a caso), check.sh (pass/fail)
  e solution.sh (la soluzione di riferimento, per `validate`), preceduti da lessons/_lib.sh.

Gli esercizi sono di due tipi:
- stato: chi si esercita cambia il sistema, check.sh verifica il risultato;
- risposta: chi si esercita scrive una risposta, check.sh la confronta con il valore vero calcolato
  sul sistema al momento del check; solution.sh stampa la risposta giusta.
Come per i ticket, si verifica il risultato, mai i comandi digitati.

Quali lezioni preparano a quale ticket lo dice lo scenario (`lessons` in scenario.toml).
"""

from __future__ import annotations

import re
import shlex
import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import sandbox
from .sandbox import CheckResult, DockerSandbox, ExecResult


LESSONS_DIR = Path(__file__).resolve().parents[2] / "lessons"
TRACKS = ("orientarsi", "permessi", "processi e memoria")
KINDS = ("stato", "risposta")
# Nell'etichetta del container: distingue un esercizio attivo da un ticket attivo.
LABEL_PREFIX = "esercizio:"
EXERCISE_KEY = re.compile(r"\d+\.\d+")
MAX_ANSWER_CHARS = 200
# Il setup sceglie a caso: un solo giro di validate proverebbe un solo caso.
VALIDATE_ROUNDS = 3


@dataclass(frozen=True)
class Exercise:
    key: str  # "5.1": lezione e posizione, è così che lo sceglie chi si esercita
    id: str  # la cartella degli script
    title: str
    kind: str
    task: str
    hints: tuple[str, ...]
    path: Path

    @property
    def lesson_number(self) -> int:
        return int(self.key.split(".")[0])

    def script(self, name: str, answer: str | None = None) -> str:
        text = (self.path / f"{name}.sh").read_text(encoding="utf-8")
        # La risposta arriva quotata: è testo di chi si esercita, non deve diventare codice.
        prefix = f"ANSWER={shlex.quote(answer)}\n" if answer is not None else ""
        return prefix + (LESSONS_DIR / "_lib.sh").read_text(encoding="utf-8") + "\n" + text


@dataclass(frozen=True)
class Lesson:
    number: int
    id: str
    title: str
    track: str
    man: tuple[str, ...]
    exercises: tuple[Exercise, ...]
    path: Path

    @property
    def explanation(self) -> str:
        return (self.path / "lesson.md").read_text(encoding="utf-8")


def load_lessons(directory: Path = LESSONS_DIR) -> list[Lesson]:
    """Le lezioni in ordine di numero: è l'ordine della roadmap."""
    lessons = []
    for toml_path in directory.glob("*/lesson.toml"):
        folder = toml_path.parent
        match = re.match(r"(\d+)-", folder.name)
        if not match:
            raise ValueError(f"{folder.name}: il nome della cartella inizia con il numero della lezione (es. 05-...)")
        number = int(match[1])
        meta = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        exercises = tuple(
            Exercise(key=f"{number}.{position}", id=e["id"], title=e["title"], kind=e["kind"],
                     task=e["task"].strip(), hints=tuple(e.get("hints", ())), path=folder / e["id"])
            for position, e in enumerate(meta["exercises"], start=1)
        )
        lesson = Lesson(number=number, id=folder.name, title=meta["title"], track=meta["track"],
                        man=tuple(meta.get("man", ())), exercises=exercises, path=folder)
        if lesson.track not in TRACKS or any(e.kind not in KINDS for e in exercises):
            raise ValueError(f"{lesson.id}: percorso o tipo di esercizio non valido")
        lessons.append(lesson)
    return sorted(lessons, key=lambda lesson: lesson.number)


def get_lesson(number: int) -> Lesson:
    for lesson in load_lessons():
        if lesson.number == number:
            return lesson
    raise KeyError(f"lezione sconosciuta: {number} (vedi `breakfix-sandbox lessons`)")


def get_exercise(key: str) -> Exercise:
    """Per chiave (5.1); il solo numero della lezione (5) vuol dire il suo primo esercizio."""
    if key.isdigit():
        key = f"{int(key)}.1"
    for lesson in load_lessons():
        for exercise in lesson.exercises:
            if exercise.key == key:
                return exercise
    raise KeyError(f"esercizio sconosciuto: {key!r} (vedi `breakfix-sandbox lessons`)")


def active_exercise() -> Exercise | None:
    label = sandbox.active_scenario()
    if not label or not label.startswith(LABEL_PREFIX):
        return None
    try:
        return get_exercise(label.removeprefix(LABEL_PREFIX))
    except KeyError:  # etichetta di un esercizio che non esiste più
        return None


class LessonLab:
    """Prepara e verifica gli esercizi nel container Docker della sandbox."""

    def __init__(self) -> None:
        self.box = DockerSandbox()

    def start(self, exercise: Exercise) -> None:
        """Container nuovo e sano, poi la preparazione dell'esercizio."""
        sandbox.reset(LABEL_PREFIX + exercise.key)
        result = self.box.run_script(exercise.script("setup"))
        if result.exit_code != 0:
            raise RuntimeError(f"{exercise.key}: la preparazione è fallita: {_output(result)}")

    def check(self, exercise: Exercise, answer: str | None = None) -> CheckResult:
        if not sandbox.is_running():
            return CheckResult(False, "FAIL: il container non è più in esecuzione")
        if exercise.kind == "risposta":
            answer = " ".join((answer or "").split())[:MAX_ANSWER_CHARS]
        else:
            answer = None
        result = self.box.run_script(exercise.script("check", answer))
        return CheckResult(result.exit_code == 0, _output(result))

    def validate(self, exercise: Exercise) -> list[str]:
        """Valido se, a ogni giro: appena preparato non passa, con la soluzione di riferimento sì."""
        for _ in range(VALIDATE_ROUNDS):
            try:
                self.start(exercise)
            except RuntimeError as exc:
                return [str(exc)]
            problems = []
            if (before := self.check(exercise, "risposta-sbagliata")).passed:
                problems.append(f"prima della soluzione il check passa: {before.output}")
            solution = self.box.run_script(exercise.script("solution"))
            if solution.exit_code != 0:
                return [*problems, f"la soluzione di riferimento è fallita: {_output(solution)}"]
            answer = solution.stdout.strip() if exercise.kind == "risposta" else None
            if not (after := self.check(exercise, answer)).passed:
                problems.append(f"con la soluzione di riferimento il check fallisce: {after.output}")
            if problems:
                return problems
        return []


def _output(result: ExecResult) -> str:
    return (result.stdout + result.stderr).strip()
