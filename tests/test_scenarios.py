"""Struttura degli scenari, senza Docker: la validazione vera è `breakfix-sandbox validate`."""

from __future__ import annotations

import hashlib
import unittest

from breakfix.guardrail import check_command
from breakfix.lab import APP_CODE, APP_DIR, CATEGORIES, DIFFICULTIES, SERVICE, SERVICE_USER, get_scenario, load_scenarios


def _commands(script: str) -> list[str]:
    return [line.strip() for line in script.splitlines() if line.strip() and not line.lstrip().startswith("#")]


class ScenarioSetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.scenarios = load_scenarios()

    def test_size_and_categories(self) -> None:
        self.assertTrue(5 <= len(self.scenarios) <= 8, len(self.scenarios))
        self.assertEqual({s.category for s in self.scenarios}, set(CATEGORIES))

    def test_every_scenario_is_complete(self) -> None:
        for s in self.scenarios:
            with self.subTest(s.id):
                self.assertTrue(s.ticket.subject and s.ticket.body.strip() and s.man)
                # Graduati: dove guardare, come verificarlo, la causa.
                self.assertGreaterEqual(len(s.hints), 3)
                for name in ("break", "check", "fix"):
                    script = s.script(name)
                    self.assertNotIn("\r", script, f"{name}.sh ha fine riga CRLF")
                    self.assertTrue(_commands(script), f"{name}.sh è vuoto")

    def test_checks_include_the_shared_baseline(self) -> None:
        for s in self.scenarios:
            with self.subTest(s.id):
                script = s.script("check")
                self.assertIn("set -e", script)
                self.assertIn("\nbaseline\n", script)
                self.assertIn("\npass ", script)

    def test_reference_fix_passes_the_guardrail(self) -> None:
        # Se il fix di riferimento venisse bloccato, il fixer non potrebbe mai risolvere lo scenario.
        for s in self.scenarios:
            for command in _commands(s.script("fix")):
                with self.subTest(s.id, command=command):
                    self.assertIsNone(check_command(command))

    def test_checks_carry_the_app_hashes_from_the_host(self) -> None:
        script = self.scenarios[0].script("check")
        for name in APP_CODE:
            digest = hashlib.sha256((APP_DIR / name).read_bytes()).hexdigest()
            self.assertIn(f"{digest}  /srv/app/{name}", script)
        self.assertIn("\n    app_unchanged\n", script)

    def test_ticket_and_hints_do_not_spoil_the_fix(self) -> None:
        # Comando + primo argomento del fix (es. "chmod 755"): né il ticket né gli indizi lo dicono.
        for s in self.scenarios:
            text = f"{s.ticket}\n" + "\n".join(s.hints)
            for command in _commands(s.script("fix")):
                with self.subTest(s.id, command=command):
                    self.assertNotIn(" ".join(command.split()[:2]), text)

    def test_tickets_name_the_service_not_where_it_lives(self) -> None:
        # Il ticket dice di cosa parla l'utente (programma e utente con cui gira), non dove sta
        # l'app né come è fatta: quello si scopre sul server. Il testo dell'utente è escluso:
        # chi scrive può citare un file (es. Andrea dell'IT che ha modificato app.conf).
        for s in self.scenarios:
            with self.subTest(s.id):
                self.assertIn(f"Programma: {SERVICE}", str(s.ticket))
                self.assertIn(f"Utente con cui gira: {SERVICE_USER}", str(s.ticket))
                added = s.task.replace(s.ticket.body.strip(), "")
                for detail in ("/srv", "run.sh", "runuser"):
                    self.assertNotIn(detail, added)

    def test_numbering_goes_from_easy_to_hard(self) -> None:
        difficulties = [DIFFICULTIES.index(s.difficulty) for s in self.scenarios]
        self.assertEqual(difficulties, sorted(difficulties))
        self.assertEqual(get_scenario("1").id, self.scenarios[0].id)
        self.assertEqual(get_scenario(self.scenarios[-1].id), self.scenarios[-1])
        with self.assertRaises(KeyError):
            get_scenario(str(len(self.scenarios) + 1))


if __name__ == "__main__":
    unittest.main()
