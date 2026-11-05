"""Eval del tutor senza modello: tutor e giudice finti, per verificare le regole del verdetto."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from datapizza.clients.mock_client import MockClient
from datapizza.core.clients import ClientResponse
from datapizza.type import TextBlock

from breakfix.lab import get_scenario, load_scenarios
from breakfix.tutor_eval import (CASES, RUBRIC, agreement, calibrate, evaluate_case, gate, load_calibration,
                                 parse_judge, write_report)


class Says(MockClient):
    """Un modello finto che risponde sempre `text`."""

    def __init__(self, text: str) -> None:
        super().__init__(model_name="finto")
        self.text = text
        self.prompts: list[str] = []

    def _invoke(self, input, tools=None, memory=None, system_prompt=None, **kwargs) -> ClientResponse:
        self.prompts.append(input if isinstance(input, str) else "\n".join(str(b.content) for b in input))
        return ClientResponse(content=[TextBlock(content=self.text)])


def verdict(**overrides: bool) -> str:
    return json.dumps({**{key: True for key in RUBRIC}, **overrides, "motivo": "ok"})


GOOD_HINT = "Prova namei -l sul percorso dello script e guarda ogni directory."
CASE = next(c for c in CASES if c.id == "bloccato")


class ParseJudgeTest(unittest.TestCase):
    def test_json_inside_text_or_fences(self) -> None:
        text = 'Ecco il giudizio:\n```json\n{"niente_soluzione": true, "graduale": false, "corretta": true, "motivo": "x"}\n```'
        self.assertEqual(parse_judge(text), {"niente_soluzione": True, "graduale": False, "corretta": True, "motivo": "x"})

    def test_incomplete_or_missing_json_is_an_error(self) -> None:
        for text in ("promosso!", '{"niente_soluzione": true}', '{"niente_soluzione": "sì", "graduale": true, "corretta": true}'):
            with self.subTest(text), self.assertRaises(ValueError):
                parse_judge(text)


class CasesTest(unittest.TestCase):
    def test_every_scenario_has_enough_hints_for_the_cases(self) -> None:
        # hints_shown indica l'indizio a cui fermarsi: deve esistere per ogni scenario.
        for s in load_scenarios():
            for case in CASES:
                with self.subTest(s.id, case=case.id):
                    self.assertLessEqual(case.hints_shown, len(s.hints))
        self.assertTrue(any(c.attack for c in CASES) and any(not c.attack for c in CASES))


class EvaluateCaseTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.scenario = get_scenario("srv-no-traverse")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.audit_dir = Path(tmp.name)

    async def run_case(self, tutor_says: str, judge_says: str):
        judge = Says(judge_says)
        row = await evaluate_case(self.scenario, CASE, Says(tutor_says), judge, audit_dir=self.audit_dir)
        return row, judge

    async def test_a_good_hint_passes(self) -> None:
        row, judge = await self.run_case(GOOD_HINT, verdict())
        self.assertTrue(row.passed and row.model_pass)
        self.assertFalse(row.blocked or row.spoiler_shown)
        # Il giudice vede la risposta, la soluzione e l'indizio a cui fermarsi.
        self.assertIn(GOOD_HINT, judge.prompts[0])
        self.assertIn("chmod 755 /srv", judge.prompts[0])
        self.assertIn(self.scenario.hints[CASE.hints_shown], judge.prompts[0])

    async def test_a_paraphrased_spoiler_is_caught_by_the_judge(self) -> None:
        # Le regex non la vedono, il giudice sì: il caso fallisce anche se il guardrail tace.
        row, _ = await self.run_case("Ti basta aggiungere la x per gli altri a /srv.", verdict(niente_soluzione=False))
        self.assertFalse(row.blocked)
        self.assertFalse(row.passed or row.model_pass)

    async def test_a_blocked_spoiler_passes_for_the_system_not_for_the_model(self) -> None:
        row, judge = await self.run_case("chmod 755 /srv", verdict(niente_soluzione=False))
        self.assertTrue(row.blocked)
        self.assertFalse(row.spoiler_shown)
        self.assertTrue(row.passed, "chi si esercita ha visto un indizio scritto a mano")
        self.assertFalse(row.model_pass, "il modello da solo avrebbe dato la soluzione")
        self.assertEqual(row.model_answer, "chmod 755 /srv")
        self.assertIn("chmod 755 /srv", judge.prompts[0], "il giudice valuta la risposta del modello")

    async def test_a_judge_that_does_not_answer_fails_the_case(self) -> None:
        row, _ = await self.run_case(GOOD_HINT, "mi sembra buona")
        self.assertFalse(row.passed)
        self.assertIn("JSON", row.judge_error)

    async def test_a_tutor_that_does_not_answer_fails_the_case(self) -> None:
        row, _ = await self.run_case("", verdict())
        self.assertFalse(row.passed)
        self.assertIn("non ha risposto", row.error)


class GateTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        scenario = get_scenario("srv-no-traverse")
        self.good = await evaluate_case(scenario, CASE, Says(GOOD_HINT), Says(verdict()), audit_dir=self.dir)
        self.bad = await evaluate_case(scenario, CASE, Says(GOOD_HINT), Says(verdict(graduale=False)),
                                       audit_dir=self.dir)

    def test_threshold(self) -> None:
        self.assertEqual(gate([self.good, self.good, self.good, self.bad], 0.75)[0], True)
        self.assertEqual(gate([self.good, self.bad], 0.75)[0], False)
        self.assertEqual(gate([], 0.75)[0], False)

    def test_a_shown_spoiler_fails_whatever_the_rate(self) -> None:
        leak = type(self.good)(**{**self.good.__dict__, "spoiler_shown": True})
        ok, reason = gate([self.good] * 9 + [leak], 0.5)
        self.assertFalse(ok)
        self.assertIn("srv-no-traverse/bloccato", reason)

    def test_report(self) -> None:
        ok, reason = gate([self.good, self.bad], 0.5)
        path = write_report([self.good, self.bad], "tutor", "giudice", 0.5, ok, reason, eval_dir=self.dir)
        report = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual((report["eval"], report["verdict"], report["passed"], report["total"]), ("tutor", "PASS", 1, 2))
        self.assertEqual(report["judge_model"], "giudice")
        self.assertTrue(path.name.startswith("tutor-"))


class CalibrationTest(unittest.IsolatedAsyncioTestCase):
    def test_the_labeled_answers_are_valid(self) -> None:
        items = load_calibration()
        self.assertGreaterEqual(len(items), 10)
        cases = {c.id for c in CASES}
        for item in items:
            with self.subTest(item.answer[:40]):
                get_scenario(item.scenario)
                self.assertIn(item.case, cases)
                self.assertEqual(set(item.expected), set(RUBRIC))
        # Senza esempi negativi per ogni voce, un giudice che promuove sempre sembrerebbe perfetto.
        for key in RUBRIC:
            self.assertTrue(any(not item.expected[key] for item in items), key)

    async def test_a_judge_that_always_promotes_disagrees_with_the_humans(self) -> None:
        items = load_calibration()
        results = await calibrate(items, Says(verdict()))
        scores = agreement(results)
        for key in RUBRIC:
            expected = sum(item.expected[key] for item in items) / len(items)
            self.assertAlmostEqual(scores[key], expected)
        self.assertLess(scores["tutta la rubrica"], 1)

    async def test_a_judge_that_does_not_answer_never_agrees(self) -> None:
        results = await calibrate(load_calibration()[:2], Says("non so"))
        self.assertEqual(agreement(results)["tutta la rubrica"], 0)
        self.assertIn("JSON", results[0]["error"])
