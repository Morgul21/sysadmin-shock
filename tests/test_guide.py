"""La ricerca nella guida: parsing del testo della Debian Reference e BM25, senza rete né modello.

In fondo, l'eval della ricerca sulla guida vera: gira solo se la guida c'è (nel container dell'app
sì, perché il Dockerfile la installa prima dei test).
"""

from __future__ import annotations

import gzip
import tempfile
import unittest
from pathlib import Path

from breakfix import guide
from breakfix.guide import MAX_PASSAGE_CHARS, GuideMissing, Index, parse, read_text, tokens

NBSP = " "

# Com'è fatto il testo del pacchetto: indice ed elenco delle tabelle in testa con spazi normali, i
# titoli veri con uno spazio non separabile, il corpo rientrato di 4 spazi, titoli lunghi a capo.
SAMPLE = f"""Debian Reference

Indice

    9.6.1. Uso dello spazio su disco
9.1. Elenco di strumenti per la gestione della memoria

Capitolo{NBSP}9.{NBSP}Suggerimenti per il sistema

9.4.1.{NBSP}Permessi dei file

    chmod(1) cambia i permessi di un file, chown(1) il proprietario.

9.6.1.{NBSP}Uso dello spazio su disco

    L'uso dello spazio su disco può essere valutato con i programmi
    forniti dai pacchetti mount e coreutils:

      * df(1) mostra l'uso dello spazio su disco da parte dei file system.

9.8.12.{NBSP}Consumo invisibile dello spazio su
disco

    Tutti i file cancellati ma aperti consumano spazio su disco,
    anche se non sono visibili con il normale comando du(1).

    # lsof -s -X / |grep deleted
"""


def sample_index() -> Index:
    return Index(parse(SAMPLE))


class ParseTest(unittest.TestCase):
    def test_sections_come_from_the_body_not_from_the_table_of_contents(self) -> None:
        passages = parse(SAMPLE)
        self.assertEqual([p.id for p in passages], ["9.4.1", "9.6.1", "9.8.12"])
        self.assertTrue(all(p.chapter == "Suggerimenti per il sistema" for p in passages))

    def test_a_long_title_continues_on_the_next_line(self) -> None:
        self.assertEqual(parse(SAMPLE)[2].title, "Consumo invisibile dello spazio su disco")

    def test_the_text_loses_the_page_indentation(self) -> None:
        text = parse(SAMPLE)[1].text
        self.assertTrue(text.startswith("L'uso dello spazio su disco"))
        self.assertIn("  * df(1)", text)

    def test_a_long_section_is_split_between_paragraphs(self) -> None:
        paragraph = "    " + "parola " * 150
        text = f"1.2.3.{NBSP}Sezione lunga\n\n" + "\n\n".join([paragraph] * 6)
        passages = parse(text)
        self.assertGreater(len(passages), 1)
        self.assertEqual([p.id for p in passages], [f"1.2.3/{n}" for n in range(1, len(passages) + 1)])
        self.assertTrue(all(len(p.text) <= MAX_PASSAGE_CHARS and p.section == "1.2.3" for p in passages))

    def test_the_package_ships_it_gzipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guida.txt.gz"
            path.write_bytes(gzip.compress(SAMPLE.encode("utf-8")))
            self.assertEqual(read_text(path), SAMPLE)


class SearchTest(unittest.TestCase):
    def test_words_are_folded_and_stemmed(self) -> None:
        self.assertEqual(tokens("Più spazio, il disco è PIENO"), tokens("piu spazi disco piena"))
        self.assertNotIn("il", tokens("il disco"))

    def test_the_most_relevant_passage_comes_first(self) -> None:
        index = sample_index()
        self.assertEqual(index.search("file cancellati che occupano ancora spazio")[0].id, "9.8.12")
        self.assertEqual(index.search("permessi di un file")[0].id, "9.4.1")
        self.assertIn(index.search("simulami il disco pieno")[0].id, {"9.6.1", "9.8.12"})

    def test_no_match_no_passage(self) -> None:
        self.assertEqual(sample_index().search("stampante wifi"), [])
        self.assertEqual(sample_index().search("simulami il"), [])

    def test_without_the_guide_the_message_says_where_to_get_it(self) -> None:
        with self.assertRaises(GuideMissing) as ctx:
            guide.load_index(Path("non-esiste.txt.gz"))
        self.assertIn("debian-reference-it", str(ctx.exception))


@unittest.skipUnless(guide.guide_path(), "Debian Reference non installata (vedi il Dockerfile)")
class RetrievalEvalTest(unittest.TestCase):
    """Per ogni richiesta, la sezione che una persona ha indicato come giusta deve stare nei primi 5.

    Le richieste sono scritte come le scriverebbe chi si esercita, non con le parole della guida.
    Limite: sono poche e scritte dopo aver visto i risultati della ricerca. Dice se una modifica alla
    ricerca peggiora casi che funzionavano, non quanto la ricerca funziona su richieste nuove."""

    EXPECTED = {
        "il disco è pieno, non c'è più spazio": "9.6.1",
        "file cancellati che occupano ancora spazio su disco": "9.8.12",
        "lo spazio su disco è finito ma non trovo i file": "9.8.12",
        "permessi del file system": "1.2.3",
        "cos'è tmpfs": "1.2.13",
        "quanta memoria usa il sistema": "9.5.10",
    }

    def test_recall_at_5(self) -> None:
        index = guide.load_index()
        misses = {query: [p.section for p in index.search(query, 5)]
                  for query, section in self.EXPECTED.items()
                  if section not in [p.section for p in index.search(query, 5)]}
        self.assertEqual(misses, {})


if __name__ == "__main__":
    unittest.main()
