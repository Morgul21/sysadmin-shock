"""Il Laboratorio senza Docker né modello: guida finta, lab finto, client scriptato.

Da garantire: una bozza nasce solo da un passaggio che il modello ha davvero ricevuto, e porta con sé
la fonte (nella tabella [fonte] e negli indizi). Il resto (validazione, copie, guardrail) è dell'author.
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

from breakfix import guide_author
from breakfix.author import TOOL_NAME, load_drafts
from breakfix.guide_author import SEARCH_TOOL, clean_request, generate, guide_hints
from test_author import FakeLab
from test_guide import sample_index


DISK_FULL = {
    "id": "data-disk-full",
    "title": "Partizione dei dati piena",
    "category": "disco",
    "difficulty": "media",
    "ticket_from": "Paola (contabilità)",
    "ticket_subject": "Il gestionale non si avvia più",
    "ticket_body": "Da stamattina il gestionale si chiude appena lo apro.\nIeri sera girava il backup.",
    "break_sh": "dd if=/dev/zero of=/srv/app/data/backup.tmp bs=1M count=16 2>/dev/null || true",
    "fix_sh": "rm /srv/app/data/backup.tmp",
    "fonte": "9.6.1",
}
REQUEST = "simulami il disco dei dati pieno"
SUMMARY = TextBlock(content="Causa: partizione dei dati piena. Rottura: un file da 16 MB. Riparazione: rm.")


class GuideClient(MockClient):
    """A ogni turno: (strumento, argomenti) oppure un testo."""

    def __init__(self, turns: list) -> None:
        super().__init__(model_name="scripted")
        self.turns = list(turns)
        self.inputs: list[str] = []
        self.system_prompts: list[str | None] = []
        self.results: list[str] = []

    def _invoke(self, input, tools=None, memory=None, system_prompt=None, **kwargs) -> ClientResponse:
        self.inputs.append("\n".join(str(block.content) for block in input))
        self.system_prompts.append(system_prompt)
        turn = self.turns.pop(0)
        if isinstance(turn, TextBlock):
            return ClientResponse(content=[turn])
        name, arguments = turn
        tool = next(t for t in tools or [] if t.name == name)
        return ClientResponse(content=[FunctionCallBlock(id=f"call-{len(self.turns)}", arguments=arguments,
                                                         name=name, tool=tool)])


class GuideGenerateTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.drafts, self.audit = Path(tmp.name) / "drafts", Path(tmp.name) / "audit"
        self.benches: list = []

    async def _generate(self, client, lab, **kwargs):
        return await generate(REQUEST, client, lab, index=sample_index(), directory=self.drafts,
                              audit_dir=self.audit, on_bench=self.benches.append, **kwargs)

    async def test_a_draft_carries_the_passage_it_comes_from(self) -> None:
        client = GuideClient([(TOOL_NAME, DISK_FULL), SUMMARY])
        lab = FakeLab([[]])
        generation = await self._generate(client, lab)
        draft = load_drafts(self.drafts)[0]
        meta = tomllib.loads((draft.path / "scenario.toml").read_text(encoding="utf-8"))
        run = json.loads(generation.audit_path.read_text(encoding="utf-8"))

        self.assertEqual(generation.draft.id, "data-disk-full")
        self.assertEqual((draft.category, draft.man), ("disco", ("Debian Reference §9.6.1",)))
        self.assertEqual((meta["fonte"]["sezione"], meta["fonte"]["richiesta"]), ("9.6.1", REQUEST))
        self.assertIn("GPL", meta["fonte"]["licenza"])
        # Gli indizi li scrive il codice dal passaggio: l'ultimo è il testo della guida.
        self.assertEqual(len(draft.hints), 3)
        self.assertIn("df(1) mostra l'uso dello spazio", draft.hints[-1])
        self.assertEqual((run["agent"], run["guide"], run["request"], run["source"]),
                         ("author", "Debian Reference", REQUEST, "9.6.1"))
        self.assertEqual(run["searches"][0]["by"], "codice")
        self.assertEqual(run["attempts"][0]["source"], "9.6.1")

    async def test_the_task_has_the_request_and_the_passages_found_for_it(self) -> None:
        client = GuideClient([(TOOL_NAME, DISK_FULL), SUMMARY])
        await self._generate(client, FakeLab([[]]))

        self.assertIn(REQUEST, client.inputs[0])
        self.assertIn("[9.6.1] Uso dello spazio su disco", client.inputs[0])
        self.assertNotIn("[9.4.1]", client.inputs[0])  # non c'entra con la richiesta
        self.assertIn(SEARCH_TOOL, client.system_prompts[0])
        self.assertNotIn("ispirato al manuale", client.system_prompts[0])
        self.assertNotIn(REQUEST, client.system_prompts[0])

    async def test_a_source_the_model_never_received_is_rejected_before_the_sandbox(self) -> None:
        # 9.4.1 esiste nella guida, ma la prima ricerca non l'ha data: va prima cercata.
        permissions = {**DISK_FULL, "id": "data-dir-readonly", "category": "permessi", "fonte": "9.4.1",
                       "break_sh": "chmod 550 /srv/app/data", "fix_sh": "chmod 750 /srv/app/data"}
        client = GuideClient([
            (TOOL_NAME, permissions),
            (SEARCH_TOOL, {"query": "permessi chmod"}),
            (TOOL_NAME, permissions),
            SUMMARY,
        ])
        lab = FakeLab([[]])
        generation = await self._generate(client, lab)

        first, second = generation.attempts
        self.assertEqual((first["tried_in_sandbox"], first["source"]), (False, "9.4.1"))
        self.assertIn("fonte '9.4.1' non valida", first["problems"][0])
        self.assertEqual(len(lab.validated), 1)  # solo il secondo tentativo arriva alla sandbox
        self.assertEqual((second["source"], generation.draft.id), ("9.4.1", "data-dir-readonly"))
        self.assertEqual([s["by"] for s in self.benches[0].searches], ["codice", "modello"])

    async def test_an_invented_source_never_becomes_a_draft(self) -> None:
        client = GuideClient([(TOOL_NAME, {**DISK_FULL, "fonte": "99.1"}), (TOOL_NAME, {**DISK_FULL, "fonte": ""}),
                              TextBlock(content="Fatto.")])
        lab = FakeLab([])
        generation = await self._generate(client, lab, max_attempts=2)

        self.assertIsNone(generation.draft)
        self.assertEqual(lab.validated, [])
        self.assertEqual(load_drafts(self.drafts) if self.drafts.exists() else [], [])

    async def test_searches_are_limited(self) -> None:
        client = GuideClient([(SEARCH_TOOL, {"query": "file cancellati"}), (SEARCH_TOOL, {"query": "df"}),
                              (TOOL_NAME, DISK_FULL), SUMMARY])
        generation = await self._generate(client, FakeLab([[]]), max_searches=1)
        run = json.loads(generation.audit_path.read_text(encoding="utf-8"))
        results = [s["attributes"]["tool_result"] for s in run["spans"] if s["type"] == "tool"]

        self.assertEqual([s["query"] for s in self.benches[0].searches], [REQUEST, "file cancellati"])
        self.assertIn("[9.8.12]", results[0])
        self.assertIn("Ricerche esaurite", results[1])
        self.assertEqual(generation.draft.id, "data-disk-full")


class RequestTest(unittest.TestCase):
    def test_the_request_is_short_and_not_empty(self) -> None:
        self.assertEqual(clean_request("  il disco è pieno \r\n"), "il disco è pieno")
        for bad in ("", "   ", "x" * (guide_author.MAX_REQUEST_CHARS + 1)):
            with self.subTest(len(bad)), self.assertRaises(ValueError):
                clean_request(bad)

    def test_hints_go_from_the_method_to_the_page_of_the_guide(self) -> None:
        passage = sample_index().by_id["9.8.12"]
        hints = guide_hints(passage)
        self.assertIn("gestionale", hints[0])
        self.assertIn("9.8.12", hints[1])
        self.assertIn(passage.text, hints[2])


if __name__ == "__main__":
    unittest.main()
