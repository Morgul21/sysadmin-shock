"""Struttura delle lezioni, senza Docker: la validazione vera è `breakfix-sandbox validate`."""

from __future__ import annotations

import unittest

from breakfix import lessons
from breakfix.lab import get_scenario, load_scenarios, tickets_for


def _commands(script: str) -> list[str]:
    return [line.strip() for line in script.splitlines() if line.strip() and not line.lstrip().startswith("#")]


class LessonSetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.lessons = lessons.load_lessons()
        self.exercises = [e for lesson in self.lessons for e in lesson.exercises]

    def test_every_lesson_is_complete(self) -> None:
        for lesson in self.lessons:
            with self.subTest(lesson.id):
                self.assertIn(lesson.track, lessons.TRACKS)
                self.assertTrue(lesson.title and lesson.man and lesson.exercises)
                self.assertTrue(lesson.explanation.strip())
                self.assertNotIn("\r", lesson.explanation)

    def test_every_exercise_is_complete(self) -> None:
        for e in self.exercises:
            with self.subTest(e.key):
                self.assertIn(e.kind, lessons.KINDS)
                self.assertTrue(e.title and e.task and e.hints)
                for name in ("setup", "check", "solution"):
                    script = e.script(name)
                    self.assertNotIn("\r", script, f"{name}.sh ha fine riga CRLF")
                    self.assertTrue(_commands((e.path / f"{name}.sh").read_text(encoding="utf-8")), f"{name}.sh è vuoto")
                check = e.script("check")
                self.assertIn("set -e", check)
                self.assertIn("\npass ", check)
                if e.kind == "risposta":
                    self.assertIn("expect_answer", check)

    def test_keys_follow_the_roadmap(self) -> None:
        numbers = [lesson.number for lesson in self.lessons]
        self.assertEqual(numbers, sorted(set(numbers)))
        for lesson in self.lessons:
            self.assertTrue(lesson.id.startswith(f"{lesson.number:02d}-"), lesson.id)
            self.assertEqual([e.key for e in lesson.exercises],
                             [f"{lesson.number}.{i}" for i in range(1, len(lesson.exercises) + 1)])
        first = self.lessons[0]
        self.assertEqual(lessons.get_exercise(str(first.number)), first.exercises[0])
        self.assertEqual(lessons.get_exercise(first.exercises[-1].key), first.exercises[-1])
        with self.assertRaises(KeyError):
            lessons.get_exercise("99.1")

    def test_task_and_hints_do_not_give_the_solution(self) -> None:
        # Più largo che per i ticket: qui il tema è il comando, e gli indizi ne nominano le opzioni
        # (es. `tail -n`). Non deve comparire il comando di soluzione già pronto da copiare.
        for e in self.exercises:
            text = e.task + "\n" + "\n".join(e.hints)
            for command in _commands((e.path / "solution.sh").read_text(encoding="utf-8")):
                ready = command.replace('"$EX', "/srv/esercizi").replace('"', "")
                with self.subTest(e.key, command=ready):
                    self.assertNotIn(ready, text)

    def test_the_answer_reaches_the_check_as_data(self) -> None:
        # La risposta è testo di chi si esercita: arriva quotata, non diventa un comando.
        script = self.exercises[0].script("check", "x'; rm -rf / #")
        self.assertTrue(script.startswith("ANSWER='x'\"'\"'; rm -rf / #'\n"), script.splitlines()[0])
        self.assertNotIn("ANSWER=", self.exercises[0].script("setup"))

    def test_lessons_prepare_for_tickets(self) -> None:
        # Il collegamento sta negli scenari; ogni lezione rimandata esiste (lo verifica load_scenarios).
        scenario = get_scenario("run-sh-noexec")
        self.assertEqual(scenario.lessons, (5, 6))
        number = [s.id for s in load_scenarios()].index(scenario.id) + 1
        for lesson_number in scenario.lessons:
            self.assertIn(number, tickets_for(lessons.get_lesson(lesson_number)))


if __name__ == "__main__":
    unittest.main()
