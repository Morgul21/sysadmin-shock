"""L'author senza Docker né API key: lab finto, client scriptato, sandbox finta.

La cosa da garantire è che nella cartella delle bozze entri solo quello che la sandbox ha
validato, e che una bozza sia uno scenario come gli altri (stesso formato, stesso check comune).
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from datapizza.clients.mock_client import MockClient
from datapizza.core.clients import ClientResponse
from datapizza.type import FunctionCallBlock, TextBlock

from breakfix import author
from breakfix.agent import AgentRunError
from breakfix.author import (NUDGE, SYMPTOM, TOOL_NAME, Draft, Manual, generate, load_drafts, prove, read_manual,
                             static_problems, write_draft)
from breakfix.lab import SCENARIOS_DIR, CheckResult, load_scenarios
from breakfix.sandbox import ExecResult


GOOD = {
    "id": "data-dir-readonly",
    "title": "Cartella dei dati in sola lettura",
    "category": "permessi",
    "difficulty": "media",
    "ticket_from": "Marco (magazzino)",
    "ticket_subject": "Il gestionale si chiude subito",
    "ticket_body": "Buongiorno, da ieri sera il gestionale si apre e si richiude da solo.\nL'ha toccato qualcuno?",
    "break_sh": "chmod 550 /srv/app/data",
    "fix_sh": "chmod 750 /srv/app/data",
}
MANUAL = Manual(ref="chmod(1)", command="chmod", text="Usage: chmod [OPTION]... MODE[,MODE]... FILE...")
BROKEN = f"{SYMPTOM}: /srv/app/run.sh: 6: cannot create /srv/app/data/last-start: Permission denied"


def _problems(**changes: str) -> list[str]:
    return static_problems(Draft.from_arguments({**GOOD, **changes}), load_scenarios(), {"run-sh-noexec", "gia-in-bozza"})


class StaticProblemsTest(unittest.TestCase):
    def test_a_good_draft_has_no_problems(self) -> None:
        self.assertEqual(_problems(), [])

    def test_a_missing_field_is_a_problem_not_an_exception(self) -> None:
        arguments = {k: v for k, v in GOOD.items() if k != "fix_sh"}
        self.assertEqual(static_problems(Draft.from_arguments(arguments), [], set()), ["campo mancante: fix_sh"])

    def test_the_id_is_new_and_well_formed(self) -> None:
        for bad in ("Data Dir", "data", "run-sh-noexec", "gia-in-bozza"):
            with self.subTest(bad):
                self.assertTrue(any("id " in p for p in _problems(id=bad)))

    def test_category_and_difficulty_are_the_known_ones(self) -> None:
        self.assertTrue(any("categoria" in p for p in _problems(category="rete")))
        self.assertTrue(any("difficoltà" in p for p in _problems(difficulty="impossibile")))

    def test_the_reference_fix_must_pass_the_guardrail(self) -> None:
        for fix in ("chmod 777 /srv/app/data", "chmod -R 750 /srv/app", "sh -c 'chmod 750 /srv/app/data'"):
            with self.subTest(fix):
                self.assertTrue(any("guardrail" in p for p in _problems(fix_sh=fix)))

    def test_the_ticket_must_not_contain_the_fix(self) -> None:
        body = "Un collega dice di fare chmod 750 sulla cartella dei dati."
        self.assertTrue(any("ticket" in p for p in _problems(ticket_body=body)))

    def test_the_break_of_an_existing_scenario_is_a_duplicate(self) -> None:
        problems = _problems(break_sh="# stessa cosa, con un commento\nchmod 644 /srv/app/run.sh")
        self.assertTrue(any("run-sh-noexec" in p for p in problems))

    def test_the_same_command_on_the_same_file_is_a_copy(self) -> None:
        # Cambiare il numero (o scrivere il percorso in un altro modo) non fa uno scenario nuovo.
        for copy in ("chmod 600 /srv/app/run.sh", "chmod a-x /srv/app/run.sh", "chmod 600 /srv/app/../app/run.sh"):
            with self.subTest(copy):
                problems = _problems(break_sh=copy, fix_sh="chmod u+x /srv/app/run.sh")
                self.assertTrue(any("rifà" in p and "run-sh-noexec" in p for p in problems), problems)
        # Un altro comando sullo stesso file è un altro guasto.
        self.assertEqual(_problems(break_sh="chgrp root /srv/app/app.conf", fix_sh="chgrp app /srv/app/app.conf"), [])

    def test_a_fix_that_contains_an_existing_one_is_a_copy(self) -> None:
        # La challenge nata da `ls`: rottura nuova, ma la riparazione è quella di conf-root-owned più un mv.
        problems = _problems(
            break_sh="mv /srv/app/app.conf /srv/app/app.conf.bak",
            fix_sh="mv /srv/app/app.conf.bak /srv/app/app.conf\nchown app:app /srv/app/app.conf\nchmod 640 /srv/app/app.conf")
        self.assertTrue(any("riparazione contiene" in p and "conf-root-owned" in p for p in problems), problems)
        self.assertEqual(_problems(break_sh="mv /srv/app/app.conf /srv/app/app.conf.bak",
                                   fix_sh="mv /srv/app/app.conf.bak /srv/app/app.conf"), [])

    def test_what_is_already_in_the_directory_counts_as_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_draft(Draft.from_arguments(GOOD), Path(tmp), man="chmod(1)", model="scripted", trace="abcd1234")
            again = Draft.from_arguments({**GOOD, "id": "data-dir-chiusa", "break_sh": "chmod 000 /srv/app/data"})
            problems = static_problems(again, load_scenarios() + load_drafts(Path(tmp)), set())
        self.assertTrue(any("data-dir-readonly" in p for p in problems), problems)

    def test_the_ticket_must_not_name_the_broken_file(self) -> None:
        moved = {"break_sh": "mv /srv/app/app.conf /srv/app/app.conf.bak", "fix_sh": "mv /srv/app/app.conf.bak /srv/app/app.conf"}
        for body in ('Alla prima riga dice "app.conf: no such file" e si blocca.', "Manca /srv/app/app.conf, credo."):
            with self.subTest(body):
                self.assertTrue(any("nomina il file" in p for p in _problems(**moved, ticket_body=body)))
        # "dati" e "app" sono anche parole di un utente: contano solo i nomi di file e i percorsi.
        self.assertEqual(_problems(ticket_body="L'app non salva più i dati, data di ieri compresa."), [])


class WriteDraftTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)

    def _write(self, **changes: str):
        draft = Draft.from_arguments({**GOOD, **changes})
        path = write_draft(draft, self.directory, man="chmod(1)", model="scripted", trace="abcd1234")
        return draft, path, load_drafts(self.directory)[0]

    def test_a_draft_is_a_scenario_like_the_others(self) -> None:
        draft, path, scenario = self._write()
        self.assertEqual((scenario.id, scenario.title, scenario.category, scenario.difficulty),
                         (draft.id, draft.title, draft.category, draft.difficulty))
        self.assertEqual(scenario.man, ("chmod(1)",))
        self.assertEqual(scenario.ticket.body.strip(), draft.ticket_body)
        self.assertEqual(scenario.script("break").strip(), draft.break_sh)
        self.assertEqual(scenario.script("fix").strip(), draft.fix_sh)
        # Il giudice non lo scrive l'author: è il check comune, come vuole test_scenarios.
        check = scenario.script("check")
        for piece in ("set -e", "\nbaseline\n", "\npass "):
            self.assertIn(piece, check)
        self.assertIn("abcd1234", (path / "scenario.toml").read_text(encoding="utf-8"))

    def test_any_text_survives_the_toml(self) -> None:
        nasty = {
            "title": 'Un "titolo" con \\ e virgolette',
            "ticket_from": "Zoë d'Angelo (IT)",
            "ticket_body": "Riga con ''' tre apici\ne\tun tab, un \\n scritto e una \"citazione\".",
        }
        draft, _, scenario = self._write(**nasty)
        self.assertEqual(scenario.title, draft.title)
        self.assertEqual(scenario.ticket.sender, draft.ticket_from)
        self.assertEqual(scenario.ticket.body.strip(), draft.ticket_body)

    def test_scripts_reach_the_container_with_lf(self) -> None:
        _, path, _ = self._write(break_sh="chmod 550 /srv/app/data\r\necho fatto\r\n")
        for name in ("break.sh", "fix.sh", "check.sh", "scenario.toml"):
            self.assertNotIn(b"\r", (path / name).read_bytes(), name)

    def test_the_symptom_is_the_message_of_the_shared_check(self) -> None:
        self.assertIn(SYMPTOM.removeprefix("FAIL: "), (SCENARIOS_DIR / "_lib.sh").read_text(encoding="utf-8"))


class FakeLab:
    """La sandbox decisa dal test: i problemi di ogni `validate`, e cosa dice il check dopo la rottura."""

    def __init__(self, verdicts: list[list[str]], broken: str = BROKEN, start_error: str | None = None) -> None:
        self.verdicts, self.broken, self.start_error = list(verdicts), broken, start_error
        self.validated: list[str] = []
        self.started: list[str] = []

    def validate(self, scenario) -> list[str]:
        self.validated.append(scenario.script("break").strip())
        return self.verdicts.pop(0)

    def start(self, scenario) -> None:
        if self.start_error:
            raise RuntimeError(self.start_error)
        self.started.append(scenario.id)

    def check(self, scenario) -> CheckResult:
        return CheckResult(self.broken.startswith("PASS"), self.broken)


class ProveTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        write_draft(Draft.from_arguments(GOOD), Path(tmp.name), man="chmod(1)", model="m", trace="t")
        self.scenario = load_drafts(Path(tmp.name))[0]

    def test_a_valid_scenario_reports_what_the_user_sees(self) -> None:
        problems, symptom = prove(FakeLab([[]]), self.scenario)
        self.assertEqual(problems, [])
        self.assertTrue(symptom.endswith("Permission denied"))
        self.assertNotIn("FAIL", symptom)

    def test_the_problems_of_validate_come_back_as_they_are(self) -> None:
        lab = FakeLab([["dopo la rottura il check passa: PASS: il gestionale riparte"]])
        self.assertEqual(prove(lab, self.scenario), (["dopo la rottura il check passa: PASS: il gestionale riparte"], ""))
        self.assertEqual(lab.started, [])

    def test_after_the_break_the_service_must_not_start(self) -> None:
        # La rottura fa fallire il check, ma per un altro motivo: non è il guasto del ticket.
        lab = FakeLab([[]], broken="FAIL: scrivibili da tutti (correzione eccessiva): /srv/app/data")
        problems, _ = prove(lab, self.scenario)
        self.assertEqual(len(problems), 1)
        self.assertIn("scrivibili da tutti", problems[0])

    def test_a_break_that_works_only_sometimes_is_rejected(self) -> None:
        problems, _ = prove(FakeLab([[]], start_error="la rottura è fallita: timeout"), self.scenario)
        self.assertIn("deterministica", problems[0])


class FakeBox:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.commands: list[str] = []

    def exec(self, command: str) -> ExecResult:
        self.commands.append(command)
        for prefix, output in self.responses.items():
            if command.startswith(prefix):
                return ExecResult(exit_code=0, stdout=output, stderr="", truncated=False)
        return ExecResult(exit_code=127, stdout="", stderr="", truncated=False)


class ReadManualTest(unittest.TestCase):
    def test_the_help_comes_from_the_sandbox(self) -> None:
        box = FakeBox({"command -v chmod": "/usr/bin/chmod\n", "chmod --help": "Usage: chmod [OPTION]...\n"})
        manual = read_manual("chmod", box)
        self.assertEqual((manual.ref, manual.command, manual.text), ("chmod(1)", "chmod", "Usage: chmod [OPTION]..."))

    def test_the_section_is_kept_or_guessed_from_the_path(self) -> None:
        box = FakeBox({"command -v": "/usr/sbin/usermod\n", "usermod --help": "Usage: usermod\n",
                       "setfacl --help": "setfacl 2.3.1\n"})
        self.assertEqual(read_manual("usermod", box).ref, "usermod(8)")
        self.assertEqual(read_manual("setfacl(1)", box).ref, "setfacl(1)")

    def test_a_man_page_on_file_replaces_the_help(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "chmod.txt"
            page.write_text("CHMOD(1)\nNAME\n  chmod - change file mode bits\n", encoding="utf-8")
            box = FakeBox({"command -v chmod": "/usr/bin/chmod\n"})
            self.assertIn("change file mode bits", read_manual("chmod(1)", box, page).text)
            self.assertEqual(len(box.commands), 1)

    def test_only_a_command_of_the_sandbox_is_accepted(self) -> None:
        box = FakeBox({})
        for bad in ("chmod; rm -rf /", "$(reboot)", "", "nonesiste"):
            with self.subTest(bad), self.assertRaises(ValueError):
                read_manual(bad, box)
        # Un nome non valido non arriva nemmeno alla shell della sandbox.
        self.assertEqual(box.commands, ["command -v nonesiste"])


class AuthorClient(MockClient):
    """Client finto: a ogni turno uno scenario da provare (dict) oppure un testo (TextBlock)."""

    def __init__(self, turns: list) -> None:
        super().__init__(model_name="scripted")
        self.turns = list(turns)
        self.inputs: list[str] = []
        self.system_prompts: list[str | None] = []

    def _invoke(self, input, tools=None, memory=None, system_prompt=None, **kwargs) -> ClientResponse:
        self.inputs.append("\n".join(str(block.content) for block in input))
        self.system_prompts.append(system_prompt)
        turn = self.turns.pop(0)
        if isinstance(turn, TextBlock):
            return ClientResponse(content=[turn])
        tool = next(t for t in tools or [] if t.name == TOOL_NAME)
        return ClientResponse(content=[FunctionCallBlock(id=f"call-{len(self.turns)}", arguments=turn,
                                                         name=tool.name, tool=tool)])


SUMMARY = TextBlock(content="Causa: data/ in sola lettura. Rottura: chmod 550. Riparazione: chmod 750.")


class GenerateTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.drafts, self.audit = Path(tmp.name) / "drafts", Path(tmp.name) / "audit"
        self.real_scenarios = [s.id for s in load_scenarios()]

    async def _generate(self, client, lab, **kwargs):
        return await generate(MANUAL, client, lab, directory=self.drafts, audit_dir=self.audit, **kwargs)

    def _saved(self) -> list[str]:
        return [p.name for p in self.drafts.glob("*")] if self.drafts.exists() else []

    async def test_only_what_the_sandbox_validated_becomes_a_draft(self) -> None:
        client = AuthorClient([
            {**GOOD, "fix_sh": "chmod 777 /srv/app/data"},  # scartato prima della sandbox
            {**GOOD, "break_sh": "chmod 750 /srv/app/data"},  # la sandbox dice che non rompe niente
            GOOD,
            SUMMARY,
        ])
        lab = FakeLab([["dopo la rottura il check passa: PASS: il gestionale riparte"], []])
        generation = await self._generate(client, lab)
        run = json.loads(generation.audit_path.read_text(encoding="utf-8"))

        self.assertEqual(generation.draft.id, "data-dir-readonly")
        self.assertEqual(self._saved(), ["data-dir-readonly"])
        self.assertEqual(load_drafts(self.drafts)[0].script("break").strip(), GOOD["break_sh"])
        self.assertEqual(lab.validated, ["chmod 750 /srv/app/data", GOOD["break_sh"]])
        self.assertEqual([a["tried_in_sandbox"] for a in generation.attempts], [False, True, True])
        self.assertEqual([bool(a["problems"]) for a in generation.attempts], [True, True, False])
        self.assertEqual(generation.answer, SUMMARY.content)
        # Gli scenari veri non si toccano: le bozze stanno altrove.
        self.assertEqual([s.id for s in load_scenarios()], self.real_scenarios)

        self.assertEqual((run["status"], run["agent"], run["manual"], run["draft"]),
                         ("ok", "author", "chmod(1)", "data-dir-readonly"))
        self.assertEqual(run["summary"]["tool_calls"], 3)
        results = [s["attributes"]["tool_result"] for s in run["spans"] if s["type"] == "tool"]
        self.assertIn("guardrail", results[0])
        self.assertIn("dopo la rottura il check passa", results[1])
        self.assertTrue(results[2].startswith("OK"))
        self.assertIn(run["trace_id"][:8], (generation.draft.path / "scenario.toml").read_text(encoding="utf-8"))

    async def test_without_a_valid_scenario_there_is_no_draft(self) -> None:
        # Il modello insiste anche a tentativi esauriti: la sandbox non viene più toccata.
        other = {**GOOD, "break_sh": "chmod 500 /srv/app/data"}
        client = AuthorClient([GOOD, other, GOOD, TextBlock(content="Fatto: scenario pronto.")])
        lab = FakeLab([["dopo il fix di riferimento il check fallisce: FAIL"]] * 2)
        generation = await self._generate(client, lab, max_attempts=2)
        run = json.loads(generation.audit_path.read_text(encoding="utf-8"))

        self.assertIsNone(generation.draft)
        self.assertEqual(self._saved(), [])
        self.assertEqual(len(generation.attempts), 2)
        self.assertEqual(len(lab.validated), 2)
        # Il modello dice "pronto", ma il verdetto è della sandbox.
        self.assertEqual(run["status"], "error")
        self.assertIn("nessuno scenario valido", run["error"])
        self.assertIsNone(run["draft"])

    async def test_text_without_a_draft_does_not_end_the_run(self) -> None:
        client = AuthorClient([TextBlock(content="Potrei togliere un permesso alla cartella dei dati."), GOOD, SUMMARY])
        generation = await self._generate(client, FakeLab([[]]))

        self.assertEqual(generation.draft.id, "data-dir-readonly")
        self.assertIn(NUDGE, client.inputs[1])

    async def test_one_valid_draft_per_run(self) -> None:
        client = AuthorClient([GOOD, {**GOOD, "id": "data-dir-altro"}, SUMMARY])
        lab = FakeLab([[]])
        generation = await self._generate(client, lab)

        self.assertEqual(self._saved(), ["data-dir-readonly"])
        self.assertEqual(len(generation.attempts), 1)
        self.assertEqual(len(lab.validated), 1)

    async def test_a_new_draft_must_differ_from_the_ones_already_there(self) -> None:
        other = {**GOOD, "id": "log-gruppo-perso", "break_sh": "chgrp root /var/log/app/app.log",
                 "fix_sh": "chgrp app /var/log/app/app.log"}
        await self._generate(AuthorClient([GOOD, SUMMARY]), FakeLab([[]]))
        # La seconda volta il modello riprova la stessa cartella con un altro numero: è una copia della
        # bozza che c'è già, scartata senza toccare la sandbox.
        copy = {**GOOD, "id": "data-dir-chiusa", "break_sh": "chmod 000 /srv/app/data"}
        lab = FakeLab([[]])
        generation = await self._generate(AuthorClient([copy, other, SUMMARY]), lab)

        self.assertIn("data-dir-readonly", generation.attempts[0]["problems"][0])
        self.assertEqual(len(lab.validated), 1)
        self.assertEqual(sorted(self._saved()), ["data-dir-readonly", "log-gruppo-perso"])

    async def test_a_rejected_break_is_not_tried_twice(self) -> None:
        # Stessi script con un altro nome: la sandbox direbbe la stessa cosa, non la si ricrea.
        useless = {**GOOD, "break_sh": "setfacl -m u:app:- /srv/app/app.conf", "fix_sh": "setfacl -b /srv/app/app.conf"}
        client = AuthorClient([useless, {**useless, "id": "conf-acl-deny"}, GOOD, SUMMARY])
        lab = FakeLab([["dopo la rottura il check passa: PASS: il gestionale riparte"], []])
        generation = await self._generate(client, lab)

        self.assertEqual(generation.draft.id, "data-dir-readonly")
        self.assertEqual([a["tried_in_sandbox"] for a in generation.attempts], [True, False, True])
        self.assertIn("già scartato", generation.attempts[1]["problems"][0])
        self.assertEqual(len(lab.validated), 2)

    async def test_a_model_error_is_audited(self) -> None:
        # MockClient solleva un'eccezione se il task contiene "exception".
        manual = Manual(ref="chmod(1)", command="chmod", text="exception")
        with self.assertRaises(AgentRunError) as ctx:
            await generate(manual, MockClient(), FakeLab([]), directory=self.drafts, audit_dir=self.audit)
        run = json.loads(ctx.exception.audit_path.read_text(encoding="utf-8"))

        self.assertEqual((run["status"], run["draft"]), ("error", None))
        self.assertEqual(self._saved(), [])

    async def test_the_manual_is_in_the_task_not_in_the_system_prompt(self) -> None:
        # Il system prompt non cambia da un manuale all'altro: lo dice anche a chi non lo sa (il modello)
        # quali scenari esistono già, e resta un prefisso riusabile tra le esecuzioni.
        client = AuthorClient([GOOD, SUMMARY])
        await self._generate(client, FakeLab([[]]))

        prompt = client.system_prompts[0]
        self.assertEqual(prompt, author.system_prompt())
        self.assertNotIn(MANUAL.text, prompt)
        self.assertIn(MANUAL.text, client.inputs[0])
        for scenario_id in self.real_scenarios:
            self.assertIn(scenario_id, prompt)


if __name__ == "__main__":
    unittest.main()
