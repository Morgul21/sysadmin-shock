"""La guida da cui il Laboratorio genera gli esercizi: la Debian Reference, divisa in passaggi e cercata con BM25.

Perché questa fonte: è libera (GPL-2+, di Osamu Aoki), è in italiano ed è un pacchetto Debian
(`debian-reference-it`) della stessa versione della sandbox (bookworm): i comandi e i percorsi che
descrive sono quelli che chi si esercita trova nel terminale. Il testo non sta nel repository:
l'immagine dell'app installa il pacchetto, e fuori dal container lo si indica con BREAKFIX_GUIDE.

Perché BM25 e non embedding: la ricerca deve girare senza rete e senza un modello in più (il
server vLLM non serve embedding), e deve dare sempre lo stesso risultato, così si può testare.
Le richieste sono fatte di parole tecniche che la guida usa così come sono (disco, spazio, inode,
df): il limite è un sinonimo che la guida non usa ("rotto" invece di "guasto"). Per questo
l'author non si ferma alla prima ricerca: ha lo strumento `cerca_nella_guida` e sceglie lui le
parole, mentre la ricerca e il controllo della fonte citata restano codice.
"""

from __future__ import annotations

import gzip
import math
import os
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .agent import STATE_DIR


SOURCE_NAME = "Debian Reference"
SOURCE_LICENSE = "GPL-2+, Osamu Aoki"
# Dove la cerca: la variabile, il pacchetto Debian (nel container dell'app), una copia in .breakfix/.
GUIDE_PATHS = (
    Path("/usr/share/debian-reference/debian-reference.it.txt.gz"),
    STATE_DIR / "guida" / "debian-reference.it.txt.gz",
)
MAX_PASSAGE_CHARS = 1800
DEFAULT_RESULTS = 5
# "9.6.1. Uso dello spazio su disco" a inizio riga. Nel testo i titoli veri hanno uno spazio non
# separabile dopo il numero; l'indice e l'elenco delle tabelle in testa uno spazio normale.
HEADING = re.compile(r"^((?:\d+|[A-Z])(?:\.\d+)+)\. (\S.*)$")
CHAPTER = re.compile(r"^(?:Capitolo|Appendice) ((?:\d+|[A-Z]))\. (\S.*)$")

# Le parole che non dicono niente dell'argomento. Corte: il resto lo fa l'IDF di BM25.
STOPWORDS = set("""
a ad al alla alle allo agli ai anche c che chi ci come con cosa da dal dalla dalle dei del della delle
dello di e ed gli ha hanno i il in la le lo ma mi ne nei nel nella nelle non o per piu po puo qui se
si sia sono su sui sul sulla tra un una uno va vi viene fare fa essere e stato stata stati mio mia
mi me te ti si quando dove perche questo questa questi queste quello quella quelli molto solo
simulami simula simulare genera generami crea creami esercizio esercizi sezione voglio vorrei
the of to and or is are be for on in with by it this that as an
""".split())


@dataclass(frozen=True)
class Passage:
    id: str  # la sezione, es. "9.6.1"; "9.6.1/2" se la sezione è lunga e divisa in più passaggi
    section: str
    title: str
    chapter: str
    text: str

    @property
    def ref(self) -> str:
        return f"{SOURCE_NAME} §{self.section} «{self.title}»"


def _fold(text: str) -> str:
    """Minuscole e senza accenti: "più" e "piu" sono la stessa parola."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def tokens(text: str) -> list[str]:
    """Le parole di un testo, con una radice grezza: senza le vocali finali "pieno" e "piena" coincidono."""
    words = []
    for word in re.findall(r"[a-z0-9_]+", _fold(text)):
        if word in STOPWORDS or len(word) < 2:
            continue
        words.append(word.rstrip("aeiou") if len(word) > 4 else word)
    return words


def _dedent(lines: list[str]) -> str:
    # Il testo del pacchetto è impaginato con 4 spazi di rientro: si tolgono, le righe restano.
    text = "\n".join(line[4:] if line.startswith("    ") else line for line in lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _split(text: str) -> list[str]:
    """Una sezione lunga in pezzi di al più MAX_PASSAGE_CHARS, tagliati tra un paragrafo e l'altro."""
    pieces, current = [], ""
    for paragraph in text.split("\n\n"):
        if current and len(current) + len(paragraph) + 2 > MAX_PASSAGE_CHARS:
            pieces.append(current)
            current = ""
        current = f"{current}\n\n{paragraph}" if current else paragraph
        while len(current) > MAX_PASSAGE_CHARS:  # un solo paragrafo enorme (es. una tabella)
            pieces.append(current[:MAX_PASSAGE_CHARS])
            current = current[MAX_PASSAGE_CHARS:]
    return [*pieces, current] if current else pieces


def parse(text: str) -> list[Passage]:
    """I passaggi del testo della guida: una sezione numerata, o un suo pezzo se è lunga."""
    passages: list[Passage] = []
    chapter, section, title, body = "", "", "", []

    def flush() -> None:
        content = _dedent(body)
        if not section or not content:
            return
        pieces = _split(content)
        for number, piece in enumerate(pieces, start=1):
            passage_id = section if len(pieces) == 1 else f"{section}/{number}"
            passages.append(Passage(passage_id, section, title, chapter, piece))

    in_title = False  # un titolo lungo continua sulla riga dopo, senza rientro
    for line in text.replace("\r\n", "\n").split("\n"):
        if match := CHAPTER.match(line):
            flush()
            chapter, section, body, in_title = match.group(2).strip(), "", [], False
        elif match := HEADING.match(line):
            flush()
            section, title, body, in_title = match.group(1), match.group(2).strip(), [], True
        elif in_title and line.strip() and not line[0].isspace():
            title = f"{title} {line.strip()}"
        else:
            in_title = False
            body.append(line)
    flush()
    return passages


class Index:
    """BM25 sui passaggi. Il titolo della sezione pesa come tre volte il testo: dice di cosa parla."""

    K1, B, TITLE_WEIGHT = 1.5, 0.75, 3

    def __init__(self, passages: list[Passage]) -> None:
        self.passages = passages
        self.by_id = {p.id: p for p in passages}
        self.terms = [Counter(tokens(p.title) * self.TITLE_WEIGHT + tokens(p.text)) for p in passages]
        self.lengths = [sum(t.values()) for t in self.terms]
        self.average = sum(self.lengths) / len(self.lengths) if passages else 0
        frequency = Counter(term for terms in self.terms for term in terms)
        n = len(passages)
        self.idf = {term: math.log(1 + (n - df + 0.5) / (df + 0.5)) for term, df in frequency.items()}

    def search(self, query: str, k: int = DEFAULT_RESULTS) -> list[Passage]:
        wanted = set(tokens(query))
        scores = []
        for position, (terms, length) in enumerate(zip(self.terms, self.lengths)):
            score = 0.0
            for term in wanted & terms.keys():
                tf = terms[term]
                score += self.idf[term] * tf * (self.K1 + 1) / (tf + self.K1 * (1 - self.B + self.B * length / self.average))
            if score > 0:
                scores.append((score, position))
        scores.sort(key=lambda pair: (-pair[0], pair[1]))
        return [self.passages[position] for _, position in scores[:k]]


def guide_path() -> Path | None:
    if configured := os.getenv("BREAKFIX_GUIDE"):
        return Path(configured)
    return next((path for path in GUIDE_PATHS if path.is_file()), None)


class GuideMissing(RuntimeError):
    pass


def read_text(path: Path) -> str:
    data = path.read_bytes()
    if data[:2] == b"\x1f\x8b":  # il pacchetto Debian la installa compressa
        data = gzip.decompress(data)
    return data.decode("utf-8", errors="replace")


@lru_cache(maxsize=1)
def load_index(path: Path | None = None) -> Index:
    """L'indice della guida, costruito alla prima ricerca (meno di un secondo) e tenuto in memoria."""
    path = path or guide_path()
    if path is None or not path.is_file():
        raise GuideMissing(
            f"{SOURCE_NAME} non trovata. Nel container dell'app c'è già (pacchetto debian-reference-it); "
            "fuori, installala con `apt install debian-reference-it` oppure copia debian-reference.it.txt.gz "
            "in .breakfix/guida/ (o indica il file con BREAKFIX_GUIDE)")
    passages = parse(read_text(path))
    if not passages:
        raise GuideMissing(f"{path}: nessuna sezione riconosciuta, non sembra il testo della {SOURCE_NAME}")
    return Index(passages)
