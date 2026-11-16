"""Il generatore senza Docker né modello: controlli statici, formato, validazione con un lab finto, agente scriptato.

Sulla sandbox vera la catena si prova con un esercizio awk scriptato (vedi il README, sezione Genera).
"""

from __future__ import annotations

import json
import tempfile
import tomllib
import unittest
from pathlib import Path

from datapizza.clients.mock_client import MockClient
from datapizza.core.clients import ClientResponse
from datapizza.type import FunctionCallBlock, TextBlock

from breakfix import generator
from breakfix.generator import (SEARCH_TOOL, TRY_TOOL, Draft, clean_request, generate, load_generated, prove,
                                static_problems, uses, write_generated)
from breakfix.sandbox import CheckResult, ExecResult
from test_guide import sample_index


AWK = {
    "id": "awk-somma-colonna",
    "title": "Sommare una colonna con awk",
    "command": "awk",
    "explanation": "awk legge un file riga per riga e divide ogni riga in campi: $1, $2, ...\n\n"
                   "```\nawk -F: '{print $1}' /etc/passwd\n```",
    "task": "In `/srv/esercizi/vendite.csv` ogni riga è prodotto,quantità. Quanti pezzi in tutto? Usa awk.",
    "hints": "Con -F, il separatore dei campi diventa la virgola.\nUna variabile in awk si somma riga per riga e si stampa in END.",
    "setup_sh": 'mkdir -p "$EX"\necho "prodotto,quantita" > "$EX/vendite.csv"\n'
                'for p in viti dadi bulloni; do echo "$p,$(rnd 1 90)" >> "$EX/vendite.csv"; done',
    "solution_sh": "awk -F, 'NR > 1 {s += $2} END {print s}' \"$EX/vendite.csv\"",
    "alternative_sh": 's=0\nfor n in $(tail -n +2 "$EX/vendite.csv" | cut -d, -f2); do s=$((s + n)); done\necho "$s"',
    "fonte": "9.6.1",
}


def found() -> dict:
    return {p.id: p for p in sample_index().passages}


def problems(**changes) -> list[str]:
    return static_problems(Draft.from_arguments({**AWK, **changes}), {"gia-usato-qui"}, found())


class StaticTest(unittest.TestCase):
    def test_a_good_draft_has_no_problems(self) -> None:
        self.assertEqual(problems(), [])

    def test_the_solution_uses_the_command_and_the_alternative_does_not(self) -> None:
        self.assertTrue(any("non usa `awk`" in p for p in problems(solution_sh="cut -d, -f2 \"$EX/vendite.csv\"")))
        self.assertTrue(any("alternative_sh usa `awk`" in p
                            for p in problems(alternative_sh="tail -n +2 x | awk -F, '{s+=$2} END {print s}'")))
        # Nominarlo in un commento o in una stringa non è usarlo.
        self.assertFalse(uses("awk", "# qui niente awk\necho awkward"))
        self.assertTrue(uses("awk", "x=$(awk '{print}' f)"))

    def test_solutions_only_read(self) -> None:
        for script in ('awk "{print}" f > /tmp/x', "rm \"$EX/vendite.csv\"; echo 3"):
            with self.subTest(script):
                self.assertTrue(any("deve solo leggere" in p for p in problems(solution_sh=script)))
        self.assertEqual(problems(solution_sh="awk -F, '{s+=$2} END {print s}' \"$EX/v.csv\" 2>/dev/null"), [])

    def test_data_must_be_random_and_stay_out_of_the_app(self) -> None:
        self.assertTrue(any("dati a caso" in p for p in problems(setup_sh='echo "viti,3" > "$EX/vendite.csv"')))
        self.assertTrue(any("/srv/app" in p for p in problems(setup_sh='echo "$(rnd 1 9)" > /srv/app/x')))
        self.assertTrue(any("guardrail" in p for p in problems(setup_sh='chmod 777 "$EX"\necho $(rnd 1 9) > "$EX/a"')))

    def test_the_source_must_be_a_passage_received(self) -> None:
        self.assertTrue(any("fonte" in p for p in problems(fonte="99.9")))

    def test_ids_hints_and_missing_fields(self) -> None:
        self.assertTrue(any("id non valido" in p for p in problems(id="Awk")))
        self.assertTrue(any("id già usato" in p for p in problems(id="gia-usato-qui")))
        self.assertTrue(any("2 indizi" in p for p in problems(hints="uno solo")))
        self.assertEqual(problems(task=""), ["campo mancante: task"])

    def test_the_request_is_short_and_not_empty(self) -> None:
        self.assertEqual(clean_request("  insegnami awk\r\n"), "insegnami awk")
        for bad in ("", "  ", "x" * 301):
            with self.subTest(len(bad)), self.assertRaises(ValueError):
                clean_request(bad)


class FormatTest(unittest.TestCase):
    def test_a_generated_exercise_is_an_answer_exercise_with_a_check_written_by_the_program(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            passage = found()["9.6.1"]
            write_generated(Draft.from_arguments(AWK), Path(tmp), passage=passage, request="insegnami awk",
                            model="m", trace="t")
            generated = load_generated(Path(tmp))[0]
            meta = tomllib.loads((generated.exercise.path / "exercise.toml").read_text(encoding="utf-8"))
            check = generated.exercise.script("check", "42")
        self.assertEqual((generated.id, generated.command, generated.exercise.kind), ("awk-somma-colonna", "awk", "risposta"))
        self.assertEqual(len(generated.exercise.hints), 2)
        self.assertEqual((meta["fonte"]["sezione"], meta["fonte"]["richiesta"]), ("9.6.1", "insegnami awk"))
        self.assertIn("GPL", generated.source["licenza"])
        # Il check: la libreria delle Basi, la risposta quotata, la soluzione dentro una funzione.
        self.assertIn("ANSWER=42", check)
        self.assertIn("solution() {", check)
        self.assertIn("awk -F, 'NR > 1", check)
        self.assertIn("Scritto dal programma", check)


class FakeLab:
    """La sandbox decisa dal test: cosa stampano soluzione e alternativa a ogni giro."""

    def __init__(self, solutions: list[str], alternatives: list[str] | None = None, *, command_exists: bool = True) -> None:
        self.solutions, self.alternatives = list(solutions), list(alternatives or solutions)
        self.command_exists, self.current = command_exists, None
        self.lines = 8
        self.box = self
        self.started = 0

    def exec(self, command: str) -> ExecResult:
        if command.startswith("find /srv/esercizi"):  # le righe di dati preparate
            return ExecResult(exit_code=0, stdout=f"{self.lines}\n", stderr="", truncated=False)
        return ExecResult(exit_code=0 if self.command_exists else 1, stdout="", stderr="", truncated=False)

    def start(self, exercise) -> None:
        self.started += 1
        self.current = (self.solutions.pop(0), self.alternatives.pop(0))

    def run(self, exercise, name: str):
        return 0, self.current[0] if name == "solution" else self.current[1]

    def check(self, exercise, answer):
        return CheckResult(answer == self.current[0], "PASS" if answer == self.current[0] else "FAIL")


class ProveTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        write_generated(Draft.from_arguments(AWK), Path(tmp.name), passage=found()["9.6.1"], request="r", model="m", trace="t")
        self.exercise = load_generated(Path(tmp.name))[0].exercise

    def test_two_witnesses_that_agree_on_random_data(self) -> None:
        self.assertEqual(prove(FakeLab(["120", "87", "143"]), self.exercise, "awk"), ([], ["120", "87", "143"]))

    def test_witnesses_that_disagree(self) -> None:
        problems, _ = prove(FakeLab(["120", "87", "143"], ["120", "86", "143"]), self.exercise, "awk")
        self.assertIn("non coincidono", problems[0])

    def test_an_answer_that_never_changes_is_not_random(self) -> None:
        problems, _ = prove(FakeLab(["42", "42", "42"]), self.exercise, "awk")
        self.assertIn("in tutti i 3 giri", problems[0])

    def test_one_line_of_data_is_not_an_exercise(self) -> None:
        # Il primo esercizio "cognomi" generato: sei `word` di fila senza a capo, un solo dipendente.
        lab = FakeLab(["2017", "1999", "2004"])
        lab.lines = 1
        self.assertIn("ne servono almeno 5", prove(lab, self.exercise, "awk")[0][0])

    def test_the_answer_written_in_the_task_or_a_missing_command(self) -> None:
        self.assertIn("testo dell'esercizio contiene", prove(FakeLab(["awk"] * 3), self.exercise, "awk")[0][0])
        self.assertIn("non c'è", prove(FakeLab(["1"], command_exists=False), self.exercise, "gawk")[0][0])


class GenClient(MockClient):
    def __init__(self, turns: list) -> None:
        super().__init__(model_name="scripted")
        self.turns = list(turns)
        self.inputs: list[str] = []

    def _invoke(self, input, tools=None, memory=None, system_prompt=None, **kwargs) -> ClientResponse:
        self.inputs.append("\n".join(str(block.content) for block in input))
        turn = self.turns.pop(0)
        if isinstance(turn, TextBlock):
            return ClientResponse(content=[turn])
        name, arguments = turn
        tool = next(t for t in tools or [] if t.name == name)
        return ClientResponse(content=[FunctionCallBlock(id=f"c{len(self.turns)}", arguments=arguments, name=name, tool=tool)])


class GenerateTest(unittest.IsolatedAsyncioTestCase):
    async def test_only_a_validated_exercise_is_saved_and_everything_is_audited(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory, audit_dir = Path(tmp) / "gen", Path(tmp) / "audit"
            client = GenClient([
                (TRY_TOOL, {**AWK, "fonte": "1.1"}),  # fonte inventata: scartato prima della sandbox
                (SEARCH_TOOL, {"query": "file cancellati"}),
                (TRY_TOOL, AWK),
                TextBlock(content="Esercizio pronto."),
            ])
            lab = FakeLab(["120", "87", "143"])
            generation = await generate("insegnami awk sullo spazio disco", client, lab, index=sample_index(),
                                        directory=directory, audit_dir=audit_dir)
            run = json.loads(generation.audit_path.read_text(encoding="utf-8"))
            saved = [g.id for g in load_generated(directory)]

        self.assertEqual(saved, ["awk-somma-colonna"])
        self.assertEqual([a["tried_in_sandbox"] for a in generation.attempts], [False, True])
        self.assertEqual(lab.started, 3)
        self.assertEqual([s["by"] for s in generation.searches], ["codice", "modello"])
        self.assertEqual((run["agent"], run["exercise"], run["status"]), ("generatore", "awk-somma-colonna", "ok"))
        self.assertIn("insegnami awk", client.inputs[0])


if __name__ == "__main__":
    unittest.main()
