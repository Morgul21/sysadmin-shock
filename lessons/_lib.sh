# Funzioni condivise dagli esercizi: il runner le antepone a setup.sh, check.sh e solution.sh.
# Un check stampa PASS/FAIL con il motivo ed esce con 0 (pass) o 1 (fail).
# set -e: un errore inatteso nel check è un FAIL, mai un PASS.
set -e

fail() { echo "FAIL: $*"; exit 1; }
pass() { echo "PASS: $*"; exit 0; }

# Dove gli esercizi preparano i loro file.
EX=/srv/esercizi

# Un elemento a caso tra gli argomenti: ogni avvio prepara un esercizio diverso,
# così la risposta va trovata sul sistema e non ricordata.
pick() { shuf -n 1 -e "$@"; }

# Lo stato di partenza che serve al check (es. i permessi prima della modifica).
# Chi si esercita è root e potrebbe leggerlo: barerebbe con se stesso, come nei ticket.
STATE=/var/lib/esercizi
save() { mkdir -p "$STATE"; printf '%s\n' "$2" > "$STATE/$1"; }
saved() { cat "$STATE/$1"; }

# La risposta scritta da chi si esercita (ANSWER la antepone il runner): senza spazi ai lati,
# in minuscolo, "sì" vale "si"; di un percorso conta il nome del file.
answer() {
    a=$(printf '%s' "$ANSWER" | tr 'A-Z' 'a-z' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//; s/ì/i/g')
    printf '%s' "${a##*/}"
}

# $1 è la risposta giusta, calcolata adesso sul sistema: se chi si esercita ha cambiato i file,
# vale lo stato attuale, non quello di partenza.
expect_answer() {
    [ -n "$ANSWER" ] || fail "manca la risposta"
    [ "$(answer)" = "$1" ] || fail "\"$ANSWER\" non è la risposta giusta"
}

# Permessi in ottale, senza zeri davanti (640, 4755).
mode() { stat -c %a "$1"; }
