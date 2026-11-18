"""La UI senza Docker: l'API e il websocket del terminale, con lab e sessione finti."""

from __future__ import annotations

import io
import json
import queue
import time
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from datapizza.clients.mock_client import MockClient
from datapizza.core.clients import ClientResponse
from datapizza.type import TextBlock
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from breakfix import web
from breakfix.lab import CheckResult, load_scenarios


FOREIGN = {"origin": "http://evil.example"}


class FakeSession:
    """La bash finta: quello che si mette in `output` arriva al browser, b"" la chiude."""

    def __init__(self, cols: int, rows: int) -> None:
        self.sizes = [(cols, rows)]
        self.written: list[bytes] = []
        self.output: queue.Queue[bytes] = queue.Queue()
        self.closed = False
        FakeSession.last = self

    def read(self) -> bytes:
        return self.output.get()

    def write(self, data: bytes) -> None:
        self.written.append(data)
        self.output.put(b"eco:" + data)

    def resize(self, cols: int, rows: int) -> None:
        self.sizes.append((cols, rows))

    def close(self) -> None:
        self.closed = True
        self.output.put(b"")


class ApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(web.app)
        self.scenarios = load_scenarios()

    def _active(self, scenario_id: str | None):
        return mock.patch("breakfix.sandbox.active_scenario", return_value=scenario_id)

    def test_the_page_and_its_assets_are_served(self) -> None:
        self.assertIn("Sysadmin Shock", self.client.get("/").text)
        for path in ("/static/app.js", "/static/app.css", "/static/vendor/xterm.min.js",
                     "/static/vendor/addon-fit.min.js", "/static/vendor/xterm.min.css"):
            with self.subTest(path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                # Mai un app.js vecchio con un index.html nuovo: il browser ricontrolla sempre.
                self.assertEqual(response.headers["cache-control"], "no-cache")

    def test_nothing_reveals_the_cause(self) -> None:
        # Come `breakfix-sandbox list`: né l'elenco né lo scenario attivo dicono id o titolo.
        listing = self.client.get("/api/scenarios").text
        for scenario in self.scenarios:
            with self.subTest(scenario.id), self._active(scenario.id):
                view = self.client.get("/api/active").text
                self.assertIn(scenario.ticket.subject, listing)
                self.assertIn(f'"number":{web.scenario_number(scenario)}', view)
                for secret in (scenario.id, scenario.title):
                    self.assertNotIn(secret, listing)
                    self.assertNotIn(secret, view)

    def test_active_scenario(self) -> None:
        with self._active(None):
            self.assertIsNone(self.client.get("/api/active").json())
        with self._active("scenario-che-non-esiste-piu"):
            self.assertIsNone(self.client.get("/api/active").json())
        with self._active("memory-hog"):
            view = self.client.get("/api/active").json()
        self.assertEqual(view["ticket"]["program"], "gestionale")
        self.assertGreaterEqual(len(view["hints"]), 3)

    def test_start_uses_the_number_of_the_list(self) -> None:
        with mock.patch.object(web.DockerLab, "__init__", return_value=None), \
                mock.patch.object(web.DockerLab, "start") as start:
            response = self.client.post("/api/start/2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(start.call_args.args[0], self.scenarios[1])
        self.assertEqual(response.json()["number"], 2)
        self.assertEqual(self.client.post(f"/api/start/{len(self.scenarios) + 1}").status_code, 404)

    def test_start_reports_docker_errors(self) -> None:
        with mock.patch.object(web.DockerLab, "__init__", return_value=None), \
                mock.patch.object(web.DockerLab, "start", side_effect=RuntimeError("la rottura è fallita")):
            response = self.client.post("/api/start/1")
        self.assertEqual(response.status_code, 503)
        self.assertIn("la rottura è fallita", response.json()["detail"])

    def test_check(self) -> None:
        with self._active(None):
            self.assertEqual(self.client.post("/api/check").status_code, 409)
        with self._active("memory-hog"), mock.patch.object(web.DockerLab, "__init__", return_value=None), \
                mock.patch.object(web.DockerLab, "check", return_value=CheckResult(True, "PASS: ok")):
            self.assertEqual(self.client.post("/api/check").json(), {"passed": True, "output": "PASS: ok"})

    def test_lessons_list_the_roadmap(self) -> None:
        listing = {lesson["number"]: lesson for lesson in self.client.get("/api/lessons").json()}
        ticket = [s.id for s in self.scenarios].index("run-sh-noexec") + 1
        self.assertEqual([e["key"] for e in listing[5]["exercises"]], ["5.1", "5.2", "5.3"])
        self.assertIn(ticket, listing[5]["tickets"])
        self.assertEqual(listing[6]["exercises"][0]["type"], "stato")
        # Le box della mappa: i comandi della lezione e, per ogni ticket, le lezioni che preparano.
        self.assertIn("ls(1)", listing[5]["man"])
        tickets = {t["number"]: t for t in self.client.get("/api/scenarios").json()}
        self.assertEqual(tickets[ticket]["lessons"], [5, 6])

    def test_the_ticket_points_to_its_lessons(self) -> None:
        with self._active("run-sh-noexec"):
            view = self.client.get("/api/active").json()
        self.assertEqual([lesson["number"] for lesson in view["lessons"]], [5, 6])

    def test_active_exercise(self) -> None:
        with self._active("esercizio:5.3"):
            view = self.client.get("/api/active").json()
        self.assertEqual((view["kind"], view["key"], view["type"], view["next"]), ("esercizio", "5.3", "risposta", None))
        self.assertIn("## Quale terna conta", view["lesson"]["explanation"])
        with self._active("esercizio:5.1"):
            self.assertEqual(self.client.get("/api/active").json()["next"], "5.2")
        with self._active("esercizio:99.1"):
            self.assertIsNone(self.client.get("/api/active").json())

    def test_learn_starts_the_exercise(self) -> None:
        with mock.patch.object(web.LessonLab, "__init__", return_value=None), \
                mock.patch.object(web.LessonLab, "start") as start:
            response = self.client.post("/api/learn/6.2")
            self.assertEqual(self.client.post("/api/learn/99.1").status_code, 404)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(start.call_args.args[0].key, "6.2")
        self.assertEqual(response.json()["lesson"]["title"], "Cambiare i permessi con chmod")

    def test_check_sends_the_answer_to_the_exercise(self) -> None:
        with self._active("esercizio:5.1"), mock.patch.object(web.LessonLab, "__init__", return_value=None), \
                mock.patch.object(web.LessonLab, "check", return_value=CheckResult(False, "FAIL: no")) as check:
            response = self.client.post("/api/check", json={"answer": "uno.sh"})
        self.assertEqual(response.json(), {"passed": False, "output": "FAIL: no"})
        exercise, answer = check.call_args.args
        self.assertEqual((exercise.key, answer), ("5.1", "uno.sh"))
        too_long = {"answer": "x" * 1000}
        with self._active("esercizio:5.1"):
            self.assertEqual(self.client.post("/api/check", json=too_long).status_code, 422)

    def test_other_sites_cannot_change_state(self) -> None:
        # Un altro sito aperto nel browser non deve poter avviare scenari né aprire la shell di root.
        with mock.patch.object(web.DockerLab, "start") as start, mock.patch.object(web.LessonLab, "start") as learn:
            self.assertEqual(self.client.post("/api/start/1", headers=FOREIGN).status_code, 403)
            self.assertEqual(self.client.post("/api/learn/5.1", headers=FOREIGN).status_code, 403)
            self.assertEqual(self.client.post("/api/check", headers=FOREIGN).status_code, 403)
        start.assert_not_called()
        learn.assert_not_called()
        with mock.patch.object(web, "TerminalSession") as session, self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect("/ws/terminal", headers=FOREIGN) as ws:
                ws.receive_bytes()
        session.assert_not_called()

    def test_the_page_itself_is_allowed(self) -> None:
        with mock.patch.object(web.DockerLab, "__init__", return_value=None), mock.patch.object(web.DockerLab, "start"):
            response = self.client.post("/api/start/1", headers={"origin": "http://testserver"})
        self.assertEqual(response.status_code, 200)


class TerminalTest(unittest.TestCase):
    def test_bytes_flow_both_ways_and_resize_reaches_the_tty(self) -> None:
        client = TestClient(web.app)
        with mock.patch.object(web, "TerminalSession", FakeSession):
            with client.websocket_connect("/ws/terminal?cols=100&rows=30") as ws:
                ws.send_json({"input": "ls\r"})
                self.assertEqual(ws.receive_bytes(), b"eco:ls\r")
                ws.send_json({"resize": [120, 40]})
                ws.send_json({"input": "è"})
                self.assertEqual(ws.receive_bytes(), "eco:è".encode())
                session = FakeSession.last
                # La pagina si chiude. Si aspetta la chiusura dal server, cioè la fine dell'handler:
                # uscendo dal `with`, il TestClient cancella l'handler, e se lo trova ancora a chiudere
                # la sessione il test fallisce a caso con CancelledError.
                ws.close()
                self.assertEqual(ws.receive()["type"], "websocket.close")
        self.assertEqual(session.sizes, [(100, 30), (120, 40)])
        self.assertTrue(session.closed, "chiusa la pagina, la sessione si chiude")

    def test_when_bash_exits_the_socket_closes(self) -> None:
        client = TestClient(web.app)
        with mock.patch.object(web, "TerminalSession", FakeSession):
            with client.websocket_connect("/ws/terminal") as ws:
                FakeSession.last.output.put(b"logout\r\n")
                FakeSession.last.output.put(b"")
                self.assertEqual(ws.receive_bytes(), b"logout\r\n")
                with self.assertRaises(WebSocketDisconnect):
                    ws.receive_bytes()

    def test_sandbox_down_is_reported_in_the_terminal(self) -> None:
        client = TestClient(web.app)
        with mock.patch.object(web, "TerminalSession", side_effect=FileNotFoundError("docker")):
            with client.websocket_connect("/ws/terminal") as ws:
                self.assertIn("Sandbox non raggiungibile", ws.receive_text())

    def test_idle_terminal_does_not_time_out(self) -> None:
        # Il socket di exec_start(socket=True) arriva col timeout del client Docker (60 s): un terminale
        # senza output per un minuto si chiudeva da solo.
        sock = mock.Mock(spec=["recv", "sendall", "settimeout", "close"])
        api = mock.Mock()
        api.exec_create.return_value = {"Id": "exec"}
        api.exec_start.return_value = sock
        with mock.patch.object(web.docker, "from_env", return_value=mock.Mock(api=api)):
            web.TerminalSession(80, 24)
        sock.settimeout.assert_called_once_with(None)




class FakeModel(MockClient):
    """Il modello del tutor: risponde `answer` e tiene il testo dei messaggi ricevuti."""

    def __init__(self, answer: str) -> None:
        super().__init__(model_name="fake")
        self.answer = answer
        self.calls: list[dict] = []

    def _invoke(self, input, tools=None, memory=None, system_prompt=None, **kwargs) -> ClientResponse:
        self.calls.append({"input": "\n".join(str(block.content) for block in input)})
        return ClientResponse(content=[TextBlock(content=self.answer)])


class TutorApiTest(unittest.TestCase):
    """Il riquadro "Chiedi al tutor": il modello è finto, la conversazione va in un file temporaneo."""

    def setUp(self) -> None:
        self.client = TestClient(web.app)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.model = FakeModel("Guarda i permessi di ogni directory del percorso con namei -l.")
        for patch in (
            mock.patch("breakfix.tutor.STATE_PATH", Path(tmp.name) / "tutor.json"),
            mock.patch.dict("os.environ", {"BREAKFIX_AUDIT_DIR": str(Path(tmp.name) / "audit")}),
            mock.patch("breakfix.tutor.recent_commands", return_value="ls -l /srv/app/run.sh"),
            mock.patch.object(web, "build_llm_client", side_effect=lambda: self.model),
            mock.patch("breakfix.sandbox.container_id", return_value="sandbox-1"),
            mock.patch("breakfix.sandbox.active_scenario", return_value="srv-no-traverse"),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def test_only_the_page_can_ask(self) -> None:
        response = self.client.post("/api/tutor", json={"question": "aiuto"}, headers=FOREIGN)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.model.calls, [])

    def test_only_tickets_have_a_tutor(self) -> None:
        for label in (None, "esercizio:5.1"):
            with self.subTest(label), mock.patch("breakfix.sandbox.active_scenario", return_value=label):
                self.assertEqual(self.client.post("/api/tutor", json={"question": "aiuto"}).status_code, 409)

    def test_empty_questions_are_rejected(self) -> None:
        for question in ("", "   "):
            with self.subTest(repr(question)):
                self.assertEqual(self.client.post("/api/tutor", json={"question": question}).status_code, 422)

    def test_the_answer_and_the_conversation(self) -> None:
        response = self.client.post("/api/tutor", json={"question": "run.sh ha la x, perché?", "hints_shown": 1})
        self.assertEqual(response.status_code, 200)
        entry = response.json()
        self.assertEqual(entry, {"question": "run.sh ha la x, perché?", "answer": self.model.answer, "blocked": False})
        # Il tutor ha visto i comandi della sandbox e gli indizi aperti nella pagina.
        self.assertIn("ls -l /srv/app/run.sh", self.model.calls[0]["input"])
        self.assertIn("Indizi che ha già visto nella pagina: 1 di 3", self.model.calls[0]["input"])
        # Ricaricando la pagina la conversazione c'è ancora; con una sandbox nuova (ticket riavviato) no.
        self.assertEqual(self.client.get("/api/tutor").json(), [entry])
        with mock.patch("breakfix.sandbox.container_id", return_value="sandbox-2"):
            self.assertEqual(self.client.get("/api/tutor").json(), [])

    def test_a_blocked_answer_is_marked(self) -> None:
        self.model.answer = "Lancia chmod 755 /srv e hai finito."
        entry = self.client.post("/api/tutor", json={"question": "dammi il comando"}).json()
        self.assertTrue(entry["blocked"])
        self.assertNotIn("chmod 755", entry["answer"])

    def test_a_model_that_does_not_answer_is_reported(self) -> None:
        self.model.answer = ""  # il tutor solleva AgentRunError: "il modello non ha risposto"
        response = self.client.post("/api/tutor", json={"question": "aiuto"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("non ha risposto", response.json()["detail"])


class FixerApiTest(unittest.TestCase):
    """ "Confronta con l'AI": modello scriptato, sandbox mock (anche per il server MCP), lab finto.
    Report degli eval e audit vanno in una cartella temporanea, all'inizio vuota."""

    def setUp(self) -> None:
        from functools import partial

        from breakfix.evaluate import evaluate_scenario
        from test_agent_trace import ScriptedClient
        from test_evaluate import FakeLab

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.eval_dir = Path(tmp.name) / "eval"
        self.lab = FakeLab(passed=True)
        self.model = ScriptedClient(
            commands=["ls -l /srv/app", "chmod 777 /srv/app/run.sh", "chmod 755 /srv/app/run.sh"],
            answer="Causa: run.sh senza bit di esecuzione. Correzione: chmod 755. Verifica: gestionale parte.",
        )
        for patch in (
            mock.patch.dict("os.environ", {"BREAKFIX_SANDBOX": "mock", "BREAKFIX_AUDIT_DIR": tmp.name}),
            mock.patch.object(web, "EVAL_DIR", self.eval_dir),
            mock.patch.object(web, "commands_typed", return_value=5),
            mock.patch.object(web, "_fixer", None),
            mock.patch.object(web, "DockerLab", lambda: self.lab),
            mock.patch.object(web, "build_llm_client", side_effect=lambda: self.model),
            mock.patch.object(web, "evaluate_scenario", partial(evaluate_scenario, audit_dir=Path(tmp.name))),
            mock.patch("breakfix.sandbox.active_scenario", return_value="run-sh-noexec"),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        # Con il context manager il loop resta vivo tra una richiesta e l'altra: il fixer gira in sottofondo.
        self.client = self.enterContext(TestClient(web.app))

    def _wait(self) -> dict:
        for _ in range(200):
            run = self.client.get("/api/fixer").json()
            if run["status"] != "running":
                return run
            time.sleep(0.05)
        self.fail("il fixer non ha finito")

    def test_the_run_is_followed_step_by_step_and_judged_by_the_check(self) -> None:
        self.assertIsNone(self.client.get("/api/fixer").json())
        response = self.client.post("/api/fixer")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "running")
        run = self._wait()

        self.assertEqual(run["status"], "done")
        self.assertEqual(self.lab.started, ["run-sh-noexec"])  # sandbox rotta da capo, come nell'eval
        self.assertEqual([s["command"] for s in run["steps"]],
                         ["ls -l /srv/app", "chmod 777 /srv/app/run.sh", "chmod 755 /srv/app/run.sh"])
        self.assertEqual([s["blocked"] for s in run["steps"]], [False, True, False])
        result = run["result"]
        self.assertTrue(result["passed"])
        self.assertEqual(result["check_output"], "PASS: ok")
        self.assertEqual((result["tool_calls"], result["blocked_by_guardrail"]), (3, 1))
        self.assertIn("chmod 755", result["answer"])

    def test_the_verdict_is_the_check_not_the_answer(self) -> None:
        self.lab.passed = False  # l'AI dice di aver riparato, il check no
        self.client.post("/api/fixer")
        result = self._wait()["result"]
        self.assertFalse(result["passed"])
        self.assertIn("Verifica", result["answer"])
        self.assertEqual(list(self.eval_dir.glob("*.json")), [])  # fallita: non si salva

    def test_a_passed_live_run_is_saved_and_survives_a_restart(self) -> None:
        self.client.post("/api/fixer")
        self._wait()
        self.assertEqual(len(list(self.eval_dir.glob("[0-9]*.json"))), 1)
        live = self.client.get("/api/fixer").json()["live"]
        self.assertEqual(live["model"], "scripted")
        self.assertTrue(live["written_at"])
        with mock.patch.object(web, "_fixer", None):  # come dopo un riavvio del server
            saved = self.client.get("/api/fixer").json()
        self.assertEqual(saved["saved"]["model"], "scripted")
        self.assertTrue(saved["result"]["passed"])
        self.assertEqual([s["command"] for s in saved["steps"]],
                         ["ls -l /srv/app", "chmod 777 /srv/app/run.sh", "chmod 755 /srv/app/run.sh"])

    def test_only_tickets_and_only_from_the_page(self) -> None:
        self.assertEqual(self.client.post("/api/fixer", headers=FOREIGN).status_code, 403)
        with mock.patch("breakfix.sandbox.active_scenario", return_value="esercizio:5.1"):
            self.assertEqual(self.client.post("/api/fixer").status_code, 409)
        self.assertEqual(self.lab.started, [])

    def test_nothing_else_starts_while_the_ai_works(self) -> None:
        with mock.patch.object(web, "_fixer", web.FixerRun(scenario="run-sh-noexec")):
            for path in ("/api/fixer", "/api/start/1", "/api/learn/1.1"):
                with self.subTest(path):
                    self.assertEqual(self.client.post(path).status_code, 409)
        self.assertEqual(self.lab.started, [])

    def test_a_finished_run_belongs_to_its_ticket(self) -> None:
        self.client.post("/api/fixer")
        self._wait()
        with mock.patch("breakfix.sandbox.active_scenario", return_value="memory-hog"):
            self.assertIsNone(self.client.get("/api/fixer").json())

    def test_without_a_live_run_the_saved_one_is_shown(self) -> None:
        import asyncio
        import json

        from breakfix.evaluate import evaluate_scenario, write_report
        from breakfix.lab import get_scenario

        # Una prova di `breakfix-eval` come le scrive lui: il report negli eval, i comandi nell'audit.
        row = asyncio.run(evaluate_scenario(get_scenario("run-sh-noexec"), self.model, self.lab))
        write_report([row], "modello-di-prova", self.eval_dir)

        saved = self.client.get("/api/fixer").json()
        self.assertEqual(saved["status"], "done")
        self.assertEqual(saved["saved"]["model"], "modello-di-prova")
        self.assertEqual([s["command"] for s in saved["steps"]],
                         ["ls -l /srv/app", "chmod 777 /srv/app/run.sh", "chmod 755 /srv/app/run.sh"])
        self.assertEqual([s["blocked"] for s in saved["steps"]], [False, True, False])
        self.assertTrue(saved["result"]["passed"])
        self.assertEqual((saved["result"]["tool_calls"], saved["your_commands"]), (3, 5))
        self.assertEqual(self.lab.started, ["run-sh-noexec"])  # solo l'eval: guardare non riavvia la sandbox

        # Una prova più recente ma fallita non sostituisce quella riuscita; da sola, si vede quella.
        failed = {"model": "modello-peggiore", "written_at": "2099-12-31T00:00:00+00:00",
                  "rows": [{"scenario": "run-sh-noexec", "passed": False, "audit_path": "C:\\altrove\\manca.json"}]}
        (self.eval_dir / "20991231-000000.json").write_text(json.dumps(failed), encoding="utf-8")
        self.assertEqual(self.client.get("/api/fixer").json()["saved"]["model"], "modello-di-prova")
        for report in self.eval_dir.glob("20[0-8]*.json"):
            report.unlink()
        alone = self.client.get("/api/fixer").json()
        self.assertEqual((alone["saved"]["model"], alone["result"]["passed"], alone["steps"]),
                         ("modello-peggiore", False, []))

        # L'esecuzione dal vivo, quando c'è, vale più di quella salvata.
        self.client.post("/api/fixer")
        self.assertIsNone(self._wait()["saved"])


class LlmApiTest(unittest.TestCase):
    """Il riquadro "Modello AI": provider e modello si scelgono nella pagina, la API key resta nel .env."""

    def setUp(self) -> None:
        import os

        self.client = TestClient(web.app)
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("LLM_", "OLLAMA_")) and k not in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                                                                     "GOOGLE_API_KEY")}
        env.update(LLM_PROVIDER="ollama", OPENAI_API_KEY="sk-segreta-di-prova")
        # Niente chiamate vere al server Ollama: il test non deve dipendere da cosa gira sulla macchina.
        self.real_served_models = web._served_models
        served = mock.patch.object(web, "_served_models", return_value=[])
        self.served = served.start()
        self.addCleanup(served.stop)
        for patch in (mock.patch.dict("os.environ", env, clear=True), mock.patch.object(web, "_llm_choice", None)):
            patch.start()
            self.addCleanup(patch.stop)

    def _provider(self, settings: dict, provider: str) -> dict:
        return next(p for p in settings["providers"] if p["id"] == provider)

    def test_without_a_choice_it_is_the_env(self) -> None:
        settings = self.client.get("/api/llm").json()
        self.assertEqual((settings["provider"], settings["model"], settings["chosen"]),
                         ("ollama", "breakfix-qwen3-8b", False))
        self.assertIn("locale", settings["destination"])
        self.assertIsNone(self._provider(settings, "openai")["unavailable"])
        self.assertIn("cloud", self._provider(settings, "openai")["destination"])

    def test_a_provider_without_key_cannot_be_chosen(self) -> None:
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            self.assertIn("OPENAI_API_KEY", self._provider(self.client.get("/api/llm").json(), "openai")["unavailable"])
            response = self.client.post("/api/llm", json={"provider": "openai"})
        self.assertEqual(response.status_code, 422)
        self.assertIsNone(web._llm_choice)

    def test_the_choice_is_used_by_tutor_and_fixer(self) -> None:
        settings = self.client.post("/api/llm", json={"provider": "openai", "model": ""}).json()
        self.assertEqual((settings["provider"], settings["model"], settings["chosen"]), ("openai", "gpt-5.6-luna", True))
        self.assertEqual(web._llm_client("tutor").model_name, "gpt-5.6-luna")
        # Tornando al provider del .env senza indicare il modello, vale quello del .env.
        with mock.patch.dict("os.environ", {"LLM_MODEL": "qwen3.8-27b",
                                            "OLLAMA_BASE_URL": "http://10.0.0.5:8000/v1"}):
            # La pagina, tornando su Ollama, propone il modello del .env, non il default del codice.
            self.assertEqual(self._provider(self.client.get("/api/llm").json(), "ollama")["default_model"],
                             "qwen3.8-27b")
            settings = self.client.post("/api/llm", json={"provider": "ollama"}).json()
            self.assertEqual(settings["model"], "qwen3.8-27b")
            self.assertEqual(settings["destination"], "al server 10.0.0.5:8000")
            self.assertEqual(web._llm_client("tutor").base_url, "http://10.0.0.5:8000/v1")

    def test_the_api_key_never_reaches_the_page(self) -> None:
        for response in (self.client.get("/api/llm"), self.client.post("/api/llm", json={"provider": "openai"})):
            self.assertNotIn("sk-segreta-di-prova", response.text)

    def test_model_suggestions(self) -> None:
        # Ollama/vLLM: il modello in uso e quelli del server; i cloud: solo il loro default, senza chiamate.
        self.served.return_value = ["llama3.2", "breakfix-qwen3-8b"]
        settings = self.client.get("/api/llm").json()
        self.assertEqual(self._provider(settings, "ollama")["models"], ["breakfix-qwen3-8b", "llama3.2"])
        self.assertEqual(self._provider(settings, "openai")["models"], ["gpt-5.6-luna"])
        self.assertEqual(self.served.call_count, 1)

    def test_google_is_not_offered(self) -> None:
        settings = self.client.get("/api/llm").json()
        self.assertNotIn("google", [p["id"] for p in settings["providers"]])
        self.assertEqual(self.client.post("/api/llm", json={"provider": "google"}).status_code, 422)

    def test_served_models_reads_the_server_and_survives_failures(self) -> None:
        body = io.BytesIO(json.dumps({"data": [{"id": "qwen3.8-27b"}, {"id": "a"}, {"nope": 1}]}).encode())
        with mock.patch.dict("os.environ", {"OLLAMA_BASE_URL": "http://10.0.0.5:8000/v1/"}), \
                mock.patch.object(web, "urlopen", return_value=body) as urlopen:
            self.assertEqual(self.real_served_models(), ["a", "qwen3.8-27b"])
        self.assertEqual(urlopen.call_args.args[0], "http://10.0.0.5:8000/v1/models")
        for failure in (OSError("connection refused"), io.BytesIO(b"<html>")):
            with self.subTest(failure), mock.patch.object(
                    web, "urlopen", **({"side_effect": failure} if isinstance(failure, Exception)
                                       else {"return_value": failure})):
                self.assertIsNone(self.real_served_models())

    def test_the_server_can_be_chosen_by_port(self) -> None:
        # Un gateway con un modello per porta: basta la porta, l'host resta quello del .env.
        with mock.patch.dict("os.environ", {"OLLAMA_BASE_URL": "http://10.0.0.5:8001/v1"}):
            settings = self.client.post("/api/llm", json={"provider": "ollama", "model": "qwen3.8-flash-next",
                                                          "base_url": "8002"}).json()
            self.assertEqual(settings["base_url"], "http://10.0.0.5:8002/v1")
            self.assertEqual(settings["env"]["base_url"], "http://10.0.0.5:8001/v1")
            self.assertEqual(settings["destination"], "al server 10.0.0.5:8002")
            self.assertEqual(web._llm_client("tutor").base_url, "http://10.0.0.5:8002/v1")
            # I suggerimenti del campo Modello vengono dal server scelto, non da quello del .env.
            self.assertEqual(web._base_url(), "http://10.0.0.5:8002/v1")
            # Lo stesso server del .env non si memorizza: vale il .env.
            self.client.post("/api/llm", json={"provider": "ollama", "model": "m", "base_url": "8001"})
            self.assertIsNone(web._llm_choice[2])

    def test_a_full_server_url_gets_v1(self) -> None:
        settings = self.client.post("/api/llm", json={"provider": "ollama", "model": "m",
                                                      "base_url": " http://gpu.lan:9000/ "}).json()
        self.assertEqual(settings["base_url"], "http://gpu.lan:9000/v1")
        self.served.assert_any_call("http://gpu.lan:9000/v1")

    def test_a_server_that_does_not_answer_is_refused(self) -> None:
        self.served.return_value = None
        response = self.client.post("/api/llm", json={"provider": "ollama", "model": "m", "base_url": "8002"})
        self.assertEqual(response.status_code, 422)
        self.assertIn("non risponde", response.json()["detail"])
        self.assertIsNone(web._llm_choice)

    def test_bad_servers_are_rejected(self) -> None:
        for url in ("ftp://h/v1", "http://user:pw@h/v1", "http://h:99999/v1", "99999", "0", "localhost",
                    "http://h/v1?x=1", "javascript:alert(1)"):
            with self.subTest(url):
                response = self.client.post("/api/llm", json={"provider": "ollama", "model": "m", "base_url": url})
                self.assertEqual(response.status_code, 422)
        self.assertIsNone(web._llm_choice)

    def test_the_server_is_only_for_ollama(self) -> None:
        self.client.post("/api/llm", json={"provider": "openai", "base_url": "http://evil.example/v1"})
        self.assertEqual(web._llm_choice, ("openai", "gpt-5.6-luna", None, None))
        self.assertNotIn(mock.call("http://evil.example/v1"), self.served.call_args_list)

    def test_the_reasoning_effort_can_be_chosen(self) -> None:
        from breakfix.agent import generation_kwargs

        with mock.patch.dict("os.environ", {"LLM_REASONING_EFFORT": "none"}):
            settings = self.client.get("/api/llm").json()
            self.assertIsNone(settings["reasoning_effort"])
            self.assertEqual(settings["env"]["reasoning_effort"], "none")
            self.assertIn("xhigh", settings["reasoning_efforts"])
            # null segue il .env, un valore lo sostituisce, "" non lo invia proprio.
            for chosen, sent in ((None, "none"), ("xhigh", "xhigh"), (" Low ", "low"), ("", None)):
                with self.subTest(chosen):
                    settings = self.client.post("/api/llm", json={"provider": "ollama", "model": "m",
                                                                  "reasoning_effort": chosen}).json()
                    self.assertEqual(settings["reasoning_effort"], chosen.strip().lower() if chosen else chosen)
                    kwargs = generation_kwargs(web._llm_client("tutor"))
                    self.assertEqual(kwargs.get("reasoning_effort"), sent)

    def test_a_bad_reasoning_effort_is_rejected(self) -> None:
        for effort in ("high; rm", "x" * 17, "élevé"):
            with self.subTest(effort):
                response = self.client.post("/api/llm", json={"provider": "ollama", "model": "m",
                                                              "reasoning_effort": effort})
                self.assertEqual(response.status_code, 422)
        self.assertIsNone(web._llm_choice)

    def test_the_reasoning_effort_is_only_for_ollama(self) -> None:
        self.client.post("/api/llm", json={"provider": "openai", "reasoning_effort": "high"})
        self.assertIsNone(web._llm_choice.reasoning_effort)

    def test_bad_requests_are_rejected(self) -> None:
        for body in ({"provider": "mistral"}, {"provider": "ollama", "model": "qwen; rm -rf /"}):
            with self.subTest(body):
                self.assertEqual(self.client.post("/api/llm", json=body).status_code, 422)
        self.assertEqual(self.client.post("/api/llm", json={"provider": "openai"}, headers=FOREIGN).status_code, 403)
        self.assertIsNone(web._llm_choice)


if __name__ == "__main__":
    unittest.main()


class OracleApiTest(unittest.TestCase):
    """L'Oracolo dalla pagina: sandbox, guida e modello finti."""

    def setUp(self) -> None:
        from test_guide import sample_index
        from test_oracolo import ANSWER, GREP, AWK, FakeBox, OracleModel

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.model = OracleModel(ANSWER)
        self.box = FakeBox({GREP: (0, "25\n"), AWK: (0, "25\n")})
        self.started = []
        for patch in (
            mock.patch.dict("os.environ", {"BREAKFIX_AUDIT_DIR": tmp.name}),
            mock.patch.object(web, "_fixer", None),
            mock.patch.object(web, "build_llm_client", side_effect=lambda: self.model),
            mock.patch.object(web.oracolo, "start", lambda: self.started.append("oracolo")),
            mock.patch.object(web.oracolo, "DockerSandbox", lambda: self.box),
            mock.patch.object(web.oracolo, "load_index", sample_index),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        self.client = TestClient(web.app)

    def _active(self, label: str | None):
        return mock.patch("breakfix.sandbox.active_scenario", return_value=label)

    def test_the_oracle_starts_its_sandbox_with_its_files(self) -> None:
        view = self.client.post("/api/oracolo/start").json()
        self.assertEqual(view["kind"], "oracolo")
        self.assertIn("/srv/oracolo/app.log", [f["path"] for f in view["files"]])
        self.assertEqual(self.started, ["oracolo"])
        with self._active("oracolo"):
            self.assertEqual(self.client.get("/api/active").json()["kind"], "oracolo")
            # Niente da verificare, niente tutor né fixer: l'Oracolo non è un esercizio.
            self.assertEqual(self.client.post("/api/check").status_code, 409)
            self.assertEqual(self.client.post("/api/tutor", json={"question": "aiuto"}).status_code, 409)

    def test_a_question_gets_commands_with_their_real_output(self) -> None:
        with self._active("oracolo"):
            answer = self.client.post("/api/oracolo", json={"question": "quanti errori nel log dello spazio su disco?"}).json()
        self.assertEqual([c["output"] for c in answer["commands"][:2]], ["25", "25"])
        self.assertIsNotNone(answer["commands"][2]["blocked"])
        self.assertEqual((answer["source"], answer["source_ok"]), ("9.6.1", True))
        self.assertTrue(answer["audit"].endswith(".json"))

    def test_only_on_its_own_files_and_only_from_the_page(self) -> None:
        with self._active("run-sh-noexec"):
            self.assertEqual(self.client.post("/api/oracolo", json={"question": "errori?"}).status_code, 409)
        with self._active("oracolo"):
            self.assertEqual(self.client.post("/api/oracolo", json={"question": "x"}, headers=FOREIGN).status_code, 403)
            self.assertEqual(self.client.post("/api/oracolo", json={"question": ""}).status_code, 422)
        self.assertEqual(self.model.inputs, [])
