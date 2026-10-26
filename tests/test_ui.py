"""La UI senza Docker: il terminale con una sandbox finta, la pagina con l'AppTest di Streamlit."""

from __future__ import annotations

import unittest
from unittest import mock

from streamlit.testing.v1 import AppTest

from breakfix import ui
from breakfix.lab import load_scenarios
from breakfix.sandbox import ExecResult


class FakeSandbox:
    def __init__(self, result: ExecResult) -> None:
        self.result = result
        self.commands: list[str] = []

    def exec(self, command: str) -> ExecResult:
        self.commands.append(command)
        return self.result


def _result(stdout: str = "", stderr: str = "", exit_code: int = 0, truncated: bool = False) -> ExecResult:
    return ExecResult(exit_code=exit_code, stdout=stdout, stderr=stderr, truncated=truncated)


class RunCommandTest(unittest.TestCase):
    def test_runs_in_the_current_directory_with_bash(self) -> None:
        box = FakeSandbox(_result(f"run.sh\n\n{ui.CWD_MARKER}/srv/app"))
        run, cwd = ui.run_command(box, "ls", "/srv/app")
        self.assertTrue(box.commands[0].startswith("bash -c "))
        self.assertIn("cd /srv/app", box.commands[0])
        self.assertEqual((run.output, run.cwd, cwd), ("run.sh", "/srv/app", "/srv/app"))

    def test_cd_changes_the_directory_of_the_next_command(self) -> None:
        run, cwd = ui.run_command(FakeSandbox(_result(f"\n{ui.CWD_MARKER}/var/log/app")), "cd /var/log/app", "/root")
        self.assertEqual((run.output, run.cwd, cwd), ("", "/root", "/var/log/app"))

    def test_keeps_the_directory_when_the_marker_is_missing(self) -> None:
        # Timeout (o `exit`): il marker non arriva, la directory resta quella di prima.
        box = FakeSandbox(_result(stderr="timeout: comando interrotto dopo 15s", exit_code=124))
        run, cwd = ui.run_command(box, "sleep 60", "/srv")
        self.assertEqual(cwd, "/srv")
        self.assertIn("timeout", run.output)
        self.assertIn("[exit 124]", str(run))

    def test_shows_stderr_and_truncation(self) -> None:
        box = FakeSandbox(_result("out\n" + ui.CWD_MARKER + "/root", "err\n", exit_code=1, truncated=True))
        run, _ = ui.run_command(box, "x", "/root")
        self.assertEqual(run.output, "[output troncato: ultimi 4000 caratteri]\nout\nerr")


class ScriptedSandbox:
    """Risponde in base all'inizio del comando: serve all'esplora file, che ne lancia più di uno."""

    def __init__(self, responses: dict[str, ExecResult]) -> None:
        self.responses = responses

    def exec(self, command: str) -> ExecResult:
        for prefix, result in self.responses.items():
            if command.startswith(prefix):
                return result
        return _result(stderr=f"inatteso: {command}", exit_code=127)


class ExplorerTest(unittest.TestCase):
    def test_lists_directories_first_and_skips_other_file_types(self) -> None:
        box = ScriptedSandbox({
            "ls -la /srv/app": _result("-rw-r----- 1 app app 30 app.conf\n"),
            "find /srv/app": _result("f run.sh\nd data\nf app.conf\nl rotto\np fifo\n"),
        })
        listing, entries = ui.list_dir(box, "/srv/app")
        self.assertIn("app.conf", listing)
        self.assertEqual(entries, [ui.Entry("data", True), ui.Entry("app.conf", False), ui.Entry("run.sh", False)])

    def test_a_missing_directory_shows_the_error(self) -> None:
        box = ScriptedSandbox({"ls -la /nope": _result(stderr="ls: cannot access '/nope'", exit_code=2)})
        self.assertEqual(ui.list_dir(box, "/nope"), ("ls: cannot access '/nope'", []))

    def test_paths_with_spaces_are_quoted(self) -> None:
        box = FakeSandbox(_result("ciao\n"))
        self.assertEqual(ui.read_file(box, "/tmp/a b"), "ciao")
        self.assertIn("'/tmp/a b'", box.commands[0])


class PageTest(unittest.TestCase):
    def _page(self, active: str | None) -> AppTest:
        page = AppTest.from_file(ui.__file__, default_timeout=10)
        with mock.patch("breakfix.sandbox.active_scenario", return_value=active):
            return page.run()

    def test_first_steps_run_in_the_terminal(self) -> None:
        output = _result(f"/usr/local/bin/gestionale\n{ui.CWD_MARKER}/root")
        with mock.patch("breakfix.sandbox.active_scenario", return_value="memory-hog"), \
                mock.patch("breakfix.sandbox.DockerSandbox.exec", return_value=output) as exec_:
            page = AppTest.from_file(ui.__file__, default_timeout=10).run()
            page.button(key="step-which gestionale").click().run()
        self.assertFalse(page.exception)
        self.assertIn("which gestionale", exec_.call_args.args[0])
        self.assertIn("root@sandbox:/root# which gestionale\n/usr/local/bin/gestionale",
                      [c.value for c in page.code])

    def test_hints_are_shown_one_at_a_time(self) -> None:
        with mock.patch("breakfix.sandbox.active_scenario", return_value="memory-hog"):
            page = AppTest.from_file(ui.__file__, default_timeout=10).run()
            page.button[[b.label for b in page.button].index("Mostra indizio 1/3")].click().run()
        self.assertEqual(len(page.info), 1)
        self.assertIn("Indizio 1/3", page.info[0].value)

    def test_without_an_active_scenario_asks_to_start_one(self) -> None:
        page = self._page(None)
        self.assertFalse(page.exception)
        self.assertIn("Avvia", page.info[0].value)

    def test_shows_the_ticket_without_spoilers(self) -> None:
        for scenario in load_scenarios():
            with self.subTest(scenario.id):
                page = self._page(scenario.id)
                self.assertFalse(page.exception)
                text = "\n".join(str(e.value) for e in (*page.markdown, *page.text, *page.caption, *page.subheader))
                text += "\n".join(page.sidebar.selectbox[0].options)
                self.assertIn(scenario.ticket.subject, text)
                self.assertIn(scenario.ticket.body.strip(), text)
                self.assertNotIn(scenario.id, text)
                self.assertNotIn(scenario.title, text)
                self.assertFalse(page.info, "nessun indizio prima di chiederlo")


if __name__ == "__main__":
    unittest.main()
