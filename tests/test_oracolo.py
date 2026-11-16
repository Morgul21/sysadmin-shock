"""L'Oracolo senza Docker né modello: file di prova, risposta del modello, controlli, esecuzione finta, eval."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from datapizza.clients.mock_client import MockClient
from datapizza.core.clients import ClientResponse
from datapizza.type import TextBlock

from breakfix import oracolo
from breakfix.agent import AgentRunError
from breakfix.oracolo import Answer, Case, ask, grade, load_cases, output_answers, parse, setup_script, why_blocked
from breakfix.sandbox import ExecResult
from test_guide import sample_index


class FakeBox:
    """La sandbox finta: l'output di ogni comando lo decide il test."""

    def __init__(self, outputs: dict[str, tuple] | None = None) -> None:
        self.outputs = outputs or {}
        self.commands: list[str] = []

    def exec(self, command: str) -> ExecResult:
        self.commands.append(command)
        code, out, *err = self.outputs.get(command, (0, ""))
        return ExecResult(exit_code=code, stdout=out, stderr=err[0] if err else "", truncated=False)

    def run_script(self, script: str, timeout: int = 60) -> ExecResult:
        return ExecResult(exit_code=0, stdout="", stderr="", truncated=False)


class OracleModel(MockClient):
    def __init__(self, answer: dict | str) -> None:
        super().__init__(model_name="oracolo-finto")
        self.answer = answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
        self.inputs: list[str] = []
        self.system_prompts: list[str | None] = []

    def _invoke(self, input, tools=None, memory=None, system_prompt=None, **kwargs) -> ClientResponse:
        self.inputs.append("\n".join(str(block.content) for block in input))
        self.system_prompts.append(system_prompt)
        return ClientResponse(content=[TextBlock(content=self.answer)])


GREP = "grep -c ' ERROR ' /srv/oracolo/app.log"
AWK = "awk '$3 == \"ERROR\"' /srv/oracolo/app.log | wc -l"
ANSWER = {
    "spiegazione": "grep cerca le righe che contengono un testo; con -c le conta invece di stamparle.",
    "comandi": [
        {"comando": GREP, "spiegazione": "conta le righe di errore",
         "opzioni": [{"parte": "-c", "significato": "conta invece di stampare"}]},
        {"comando": AWK, "spiegazione": "le stesse righe con awk, poi le conta",
         "opzioni": [{"parte": "$3", "significato": "il terzo campo, il livello"}]},
        {"comando": "rm /srv/oracolo/app.log", "spiegazione": "per sicurezza", "opzioni": []},
    ],
    "fonte": "9.6.1",
    "nota": "grep è il più diretto",
}


class DataTest(unittest.TestCase):
    def test_the_setup_writes_every_file_and_the_archive(self) -> None:
        script = setup_script()
        for name in oracolo.DATA_FILES:
            with self.subTest(name):
                self.assertIn(f"cat > /srv/oracolo/{name} <<'ORACOLO_EOF'", script)
        self.assertIn("head -c", script)
        self.assertIn("touch -d", script)
        # Il delimitatore non compare nei dati: un heredoc chiuso a metà troncherebbe un file.
        for name in oracolo.DATA_FILES:
            self.assertNotIn("ORACOLO_EOF", (oracolo.DATA_DIR / name).read_text(encoding="utf-8"))

    def test_the_preview_shows_formats_not_answers(self) -> None:
        text = oracolo.preview()
        self.assertIn("cognome,nome,reparto,anno_assunzione,citta", text)
        self.assertIn("/srv/oracolo/archivio/", text)
        self.assertLess(len(text), 2500)

    def test_every_eval_case_is_well_formed(self) -> None:
        cases = load_cases()
        self.assertGreaterEqual(len(cases), 10)
        self.assertEqual(len({c.id for c in cases}), len(cases))
        for case in cases:
            with self.subTest(case.id):
                self.assertIn(case.match, ("uguale", "riga"))
                self.assertIsNone(why_blocked(case.reference))  # anche i riferimenti solo leggono


class ParseAndCheckTest(unittest.TestCase):
    def test_commands_options_source_and_note(self) -> None:
        commands, source, note, explanation = parse("Ecco: " + json.dumps(ANSWER))
        self.assertEqual([c.command for c in commands][:2], [GREP, AWK])
        self.assertEqual(commands[0].options, [{"parte": "-c", "significato": "conta invece di stampare"}])
        self.assertEqual((source, note), ("9.6.1", "grep è il più diretto"))
        self.assertTrue(explanation.startswith("grep cerca"))
        renamed = {"comandi": [{"comando": "wc -l f", "opzioni": [{"parte": "-l", "significance": "conta le righe"}]}]}
        self.assertEqual(parse(json.dumps(renamed)).commands[0].options[0]["significato"], "conta le righe")
        with self.assertRaises(ValueError):
            parse("niente json")

    def test_reasoning_before_the_json_is_skipped(self) -> None:
        """Un eval è fallito così: il modello ragionava prima, e `{c++}` di awk sembrava l'inizio del JSON."""
        text = ("Userò awk: `awk 'NR>1 && $4>=2020 {c++} END {print c}'`.\n\n```json\n"
                + json.dumps(ANSWER, ensure_ascii=False) + "\n```")
        self.assertEqual(parse(text).source, "9.6.1")

    def test_a_missing_comma_does_not_turn_a_command_into_the_answer(self) -> None:
        """Un altro eval: virgola dimenticata dopo un "comando", e il parser prendeva il primo comando (che ha una
        "spiegazione") per la risposta intera: zero comandi."""
        text = json.dumps(ANSWER, ensure_ascii=False, indent=2).replace(f'"comando": "{oracolo.json.dumps(AWK)[1:-1]}",',
                                                                        f'"comando": "{oracolo.json.dumps(AWK)[1:-1]}"', 1)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(text)
        self.assertEqual([c.command for c in parse(text).commands][:2], [GREP, AWK])

    def test_the_programs_a_command_runs(self) -> None:
        self.assertEqual(oracolo.programs("journalctl -u nginx | tail -n 20"), ["journalctl", "tail"])
        self.assertEqual(oracolo.programs("LC_ALL=C sort f && wc -l f; echo 'a | b'"), ["sort", "wc", "echo"])

    def test_only_commands_that_read_are_run(self) -> None:
        for command in ("rm /srv/oracolo/app.log", "sed -i 's/a/b/' /srv/oracolo/app.log", "grep x f > /tmp/y",
                        "chmod 777 /srv", "sudo cat /etc/shadow", "echo ok | sh -c 'rm -rf /'"):
            with self.subTest(command):
                self.assertIsNotNone(why_blocked(command))
        for command in (GREP, AWK, "awk -F, 'NR > 1 { print $5 }' /srv/oracolo/dipendenti.csv",
                        "grep ERROR /srv/oracolo/app.log 2>/dev/null", "du -s /srv/oracolo/archivio/* | sort -n"):
            with self.subTest(command):
                self.assertIsNone(why_blocked(command))


class AskTest(unittest.IsolatedAsyncioTestCase):
    async def _ask(self, answer, box: FakeBox):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        model = OracleModel(answer)
        result = await ask("quanti errori ci sono nel log dello spazio su disco?", model, box=box,
                           index=sample_index(), audit_dir=Path(tmp.name))
        return result, model

    async def test_commands_are_run_and_shown_with_their_real_output(self) -> None:
        box = FakeBox({GREP: (0, "25\n"), AWK: (0, "25\n")})
        answer, model = await self._ask(ANSWER, box)
        run = json.loads(answer.audit_path.read_text(encoding="utf-8"))

        # prima quali programmi mancano, poi i comandi; rm non arriva alla sandbox
        self.assertEqual(box.commands, [oracolo.availability_check(["grep", "awk", "wc"]), GREP, AWK])
        self.assertTrue(answer.explanation.startswith("grep cerca"))
        self.assertEqual([c.output for c in answer.commands[:2]], ["25", "25"])
        self.assertIn("non solo lettura", answer.commands[2].blocked)
        self.assertTrue(answer.source_ok)
        self.assertEqual(answer.source_title, "Uso dello spazio su disco")
        # RAG: i passaggi recuperati sono nel messaggio, le anteprime dei file nel system prompt.
        self.assertIn("[9.6.1] Uso dello spazio su disco", model.inputs[0])
        self.assertIn("/srv/oracolo/dipendenti.csv", model.system_prompts[0])
        self.assertEqual((run["agent"], run["source_ok"]), ("oracolo", True))
        self.assertIn("9.6.1", run["retrieved"])

    async def test_a_program_missing_from_the_sandbox_is_shown_not_run(self) -> None:
        """journalctl in un container senza systemd: "comando non trovato" direbbe che il comando è sbagliato."""
        journal = "journalctl -u gestionale | tail -n 20"
        check = oracolo.availability_check(["journalctl", "tail", "grep"])
        box = FakeBox({check: (0, "journalctl\n")})
        answer, _ = await self._ask({**ANSWER, "comandi": [{"comando": journal, "spiegazione": "", "opzioni": []},
                                                          {"comando": GREP, "spiegazione": "", "opzioni": []}]}, box)
        self.assertEqual(box.commands, [check, GREP])
        self.assertIn("journalctl non c'è nella sandbox", answer.commands[0].unavailable)
        self.assertIsNone(answer.commands[0].exit_code)

    async def test_a_pipeline_that_writes_to_stderr_is_not_a_success(self) -> None:
        find = "find /srv/oracolo/archivio ! -newer /srv/oracolo/rif | wc -l"
        box = FakeBox({find: (0, "0\n", "find: '/srv/oracolo/rif': No such file or directory\n")})
        answer, _ = await self._ask({**ANSWER, "comandi": [{"comando": find, "spiegazione": "", "opzioni": []}]}, box)
        self.assertEqual(answer.commands[0].exit_code, 0)
        self.assertTrue(answer.commands[0].stderr)
        self.assertIn("No such file", answer.commands[0].output)

    async def test_a_source_that_was_not_retrieved_is_flagged(self) -> None:
        answer, _ = await self._ask({**ANSWER, "fonte": "4.2.1"}, FakeBox())
        self.assertFalse(answer.source_ok)

    async def test_a_model_that_does_not_answer_with_json_is_audited(self) -> None:
        with self.assertRaises(AgentRunError) as ctx:
            await self._ask("non so", FakeBox())
        self.assertIn("JSON", str(ctx.exception))


class GradeTest(unittest.TestCase):
    def _answer(self, *outputs: tuple[int | None, str]) -> Answer:
        commands = [oracolo.Command(f"cmd{i}", "", [], exit_code=code, output=out) for i, (code, out) in enumerate(outputs)]
        return Answer("q", commands, "1.1", True, "", "", [], Path("a.json"), "m")

    def test_one_right_command_is_enough_and_only_the_output_counts(self) -> None:
        case = Case("c", "q", "25", "uguale", "")
        self.assertTrue(grade(self._answer((0, "grep: errore"), (0, " 25 ")), case)["passed"])
        self.assertFalse(grade(self._answer((0, "25 righe")), case)["passed"])
        self.assertFalse(grade(self._answer((1, "25")), case)["passed"])  # uscito con errore

    def test_a_line_that_contains_the_answer(self) -> None:
        case = Case("c", "q", "Firenze", "riga", "")
        self.assertTrue(output_answers("      9 Firenze\n", case))
        self.assertFalse(output_answers("9 Firenze\n8 Roma\n", case))  # più righe: non ha risposto
        self.assertFalse(output_answers("Firenzeee", case))
        self.assertTrue(output_answers("26938\t/srv/oracolo/archivio/backup", Case("d", "q", "backup", "riga", "")))


class RetrievalTest(unittest.TestCase):
    def test_questions_are_expanded_with_the_words_of_the_commands(self) -> None:
        from breakfix.oracolo import expansion

        self.assertIn("wc contare righe", expansion("Quanti dipendenti lavorano in IT?"))
        self.assertTrue(any("awk" in t for t in expansion("Quanti dipendenti lavorano in IT?")))
        self.assertTrue(any("find" in t for t in expansion("file modificati prima del 1 agosto")))
        self.assertTrue(any("dmesg" in t for t in expansion("cosa ha fatto l'OOM killer?")))
        self.assertEqual(expansion("ciao"), [])

    @unittest.skipUnless(__import__("breakfix.guide", fromlist=["guide_path"]).guide_path(), "guida non installata")
    def test_every_eval_question_finds_the_section_of_its_command(self) -> None:
        """Il primo eval (7/13) falliva per questo: senza il passaggio sul comando, il modello rinunciava."""
        from breakfix.guide import load_index
        from breakfix.oracolo import retrieve

        sections = {"log": "1.6.2", "dipendenti": "1.6.5", "kernel": "3.3", "disco-cartella": "9.6.1",
                    "disco-file-grandi": "9.6.1", "disco-file-vecchi": "10.1.5"}
        index = load_index()
        for case in load_cases():
            prefix = next(key for key in sections if case.id.startswith(key))
            with self.subTest(case.id):
                found = {p.section for p in retrieve(case.question, index)[0]}
                self.assertIn(sections[prefix], found)


if __name__ == "__main__":
    unittest.main()
