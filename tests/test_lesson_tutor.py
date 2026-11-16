"""Il tutor delle Basi senza Docker né modello: il guardrail ricavato dalle soluzioni dei 39 esercizi."""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from breakfix import lessons
from breakfix.lesson_tutor import (ExerciseTopic, Signature, answer_spoiler, ask, secret_signatures, signatures)
from test_tutor import CannedClient


def exercise(key: str) -> lessons.Exercise:
    return lessons.get_exercise(key)


ALL = [e for lesson in lessons.load_lessons() for e in lesson.exercises]
# Dove il guardrail sul comando non può aiutare: la soluzione è la sintassi della lezione (un redirect)
# o un calcolo senza argomenti da nascondere (la risposta la protegge il valore).
NO_COMMAND_SECRET = {"4.2", "4.3", "5.3", "8.1", "8.2", "11.1", "11.2"}
# Comandi che cambiano il sistema: negli esercizi a risposta solution.sh gira anche durante la
# lezione (per il guardrail), quindi deve soltanto leggere.
WRITES = re.compile(r"\b(chmod|chown|chgrp|setfacl|rm|mv|cp|touch|mkdir|kill|pkill|tee|truncate|dd)\b"
                    r"|(?<![2&])>(?!\s*/dev/null)")


class SignatureTest(unittest.TestCase):
    def test_commands_keep_their_literal_arguments(self) -> None:
        script = 'chmod 640 "$EX/dati.txt"\nchown -R app:app "$EX/sito"\nkill -9 "$(pgrep -f /opt/x.py)"\n'
        self.assertEqual({str(s) for s in signatures(script)},
                         {"chmod 640", "chown -R app:app", "kill -9", "pgrep -f"})

    def test_loops_functions_and_service_commands_are_not_secrets(self) -> None:
        script = ('blocked() {\n  for p in "$EX" "$EX/a"; do\n    runuser -u app -- test -x "$p" || { echo "$p"; return; }\n'
                  '  done\n}\nchmod o+x "$(blocked)"\nsleep 0.5\n')
        self.assertEqual({str(s) for s in signatures(script)}, {"runuser -u app", "chmod o+x"})

    def test_paths_and_markup_in_between_do_not_hide_the_command(self) -> None:
        pattern = Signature("setfacl", ("-m", "u:anna:r")).pattern()
        self.assertTrue(pattern.search("prova setfacl -m u:anna:r /srv/esercizi/bilancio.csv"))
        self.assertTrue(pattern.search("setfacl /srv/x -m u:anna:r"))
        self.assertFalse(pattern.search("setfacl -m u:anna:rw"))  # un altro permesso non è la soluzione
        self.assertFalse(pattern.search("setfacl -m\nu:anna:r"))  # su righe diverse


class SecretsTest(unittest.TestCase):
    def test_every_exercise_is_protected_by_the_answer_or_by_the_command(self) -> None:
        # Senza un comando da proteggere resta la risposta (esercizi a risposta), tranne i due redirect.
        unprotected = {e.key for e in ALL if not secret_signatures(e) and e.kind != "risposta"}
        self.assertEqual(unprotected, {"4.2", "4.3"})
        self.assertEqual({e.key for e in ALL if not secret_signatures(e)}, NO_COMMAND_SECRET)

    def test_what_the_exercise_already_says_is_not_a_secret(self) -> None:
        for e in ALL:
            public = "\n".join((e.task, *e.hints))
            for signature in secret_signatures(e):
                with self.subTest(e.key, signature=str(signature)):
                    self.assertIsNone(signature.pattern().search(public))

    def test_values_stay_secret_even_if_the_lesson_shows_them(self) -> None:
        self.assertIn("chmod 640", [str(s) for s in secret_signatures(exercise("6.1"))])
        self.assertIn("chown anna:tecnici", [str(s) for s in secret_signatures(exercise("7.3"))])

    def test_answer_solutions_only_read(self) -> None:
        for e in ALL:
            if e.kind != "risposta":
                continue
            with self.subTest(e.key):
                script = (e.path / "solution.sh").read_text(encoding="utf-8")
                code = "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("#"))
                self.assertIsNone(WRITES.search(code), f"{e.key}: solution.sh scrive")


class AnswerTest(unittest.TestCase):
    def test_the_answer_is_found_as_a_whole_word(self) -> None:
        self.assertEqual(answer_spoiler("Sono 87 file in tutto.", "87"), "87")
        self.assertIsNone(answer_spoiler("Sono 870 file, o 187.", "87"))
        self.assertEqual(answer_spoiler("Il percorso è /srv/esercizi/a/b, lì si blocca.", "/srv/esercizi/a/b"),
                         "/srv/esercizi/a/b")
        self.assertEqual(answer_spoiler("Sono .bashrc e .config", ".config\n.profile"), ".config")

    def test_yes_and_no_cannot_be_searched(self) -> None:
        self.assertIsNone(answer_spoiler("Sì, prova con runuser. No, non serve sudo.", "si"))
        self.assertIsNone(answer_spoiler("qualcosa", None))


class TopicTest(unittest.TestCase):
    def test_the_prompt_has_the_lesson_and_a_secret_solution(self) -> None:
        topic = ExerciseTopic(exercise("6.1"))
        prompt = topic.system_prompt()
        self.assertIn(lessons.get_lesson(6).title, prompt)
        self.assertIn(exercise("6.1").task, prompt)
        self.assertIn("SEGRETA", prompt)
        self.assertIn("chmod 640", prompt)
        self.assertEqual(topic.id, "esercizio:6.1")

    def test_the_spoiler_names_what_it_found(self) -> None:
        self.assertEqual(ExerciseTopic(exercise("6.1")).find_spoiler("fai `chmod` **640** dati.txt"),
                         "comando della soluzione: chmod 640")
        self.assertEqual(ExerciseTopic(exercise("4.1"), "87").find_spoiler("sono 87"), "risposta: 87")
        self.assertIsNone(ExerciseTopic(exercise("6.1")).find_spoiler("Con chmod 755 su un altro file: rwxr-xr-x."))


class AskTest(unittest.IsolatedAsyncioTestCase):
    async def test_a_spoiler_is_replaced_by_the_next_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reply = await ask(exercise("7.3"), "dammi il comando", CannedClient("chown anna:tecnici config.ini"),
                              hints_shown=1, audit_dir=Path(tmp))
            self.assertTrue(reply.blocked)
            self.assertIn(exercise("7.3").hints[1], reply.text)
            self.assertNotIn("anna:tecnici", reply.text)


if __name__ == "__main__":
    unittest.main()
