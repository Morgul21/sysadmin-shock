"""La UI senza Docker: l'API e il websocket del terminale, con lab e sessione finti."""

from __future__ import annotations

import queue
import unittest
from unittest import mock

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
                self.assertEqual(self.client.get(path).status_code, 200)

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

    def test_other_sites_cannot_change_state(self) -> None:
        # Un altro sito aperto nel browser non deve poter avviare scenari né aprire la shell di root.
        with mock.patch.object(web.DockerLab, "start") as start:
            self.assertEqual(self.client.post("/api/start/1", headers=FOREIGN).status_code, 403)
            self.assertEqual(self.client.post("/api/check", headers=FOREIGN).status_code, 403)
        start.assert_not_called()
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


if __name__ == "__main__":
    unittest.main()
