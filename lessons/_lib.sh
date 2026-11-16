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
# Un numero a caso tra $1 e $2, e una parola a caso di sei caratteri (per codici e id).
rnd() { shuf -i "$1-$2" -n 1; }
word() { tr -dc 'a-z0-9' < /dev/urandom | head -c 6; }

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

# Per le risposte che sono un percorso: conta il percorso intero, senza la / finale.
# Gli argomenti sono i percorsi giusti (es. la cartella, o il file al suo interno).
expect_path() {
    [ -n "$ANSWER" ] || fail "manca la risposta"
    given=$(printf '%s' "$ANSWER" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//; s:/*$::')
    for right in "$@"; do
        [ "$given" = "$right" ] && return 0
    done
    fail "\"$ANSWER\" non è il percorso giusto (scrivi il percorso completo, che inizia con /)"
}

# Avvia /opt/lavori/<nome>.py in background: occupa <MB> di memoria e resta in attesa; con un terzo
# argomento ignora il segnale TERM. setsid e i redirect lo staccano dal setup, che può finire.
# Aspetta che la memoria sia occupata davvero, altrimenti il check vedrebbe un processo vuoto.
job() {
    mkdir -p /opt/lavori
    {
        echo "import signal, time"
        [ -z "$3" ] || echo "signal.signal(signal.SIGTERM, signal.SIG_IGN)"
        echo "data = 'x' * ($2 * 2**20)"
        echo "while True:"
        echo "    time.sleep(3600)"
    } > "/opt/lavori/$1.py"
    setsid nohup python3 "/opt/lavori/$1.py" < /dev/null > /dev/null 2>&1 &
    for _ in $(seq 40); do
        rss=$(ps -o rss= -p "$(pgrep -f "/opt/lavori/$1.py" | head -1)" 2>/dev/null | tr -d ' ') || rss=0
        [ "${rss:-0}" -gt $(( $2 * 900 )) ] && return 0
        sleep 0.25
    done
    echo "il lavoro $1 non ha occupato la memoria" >&2
    exit 1
}

# Permessi in ottale, senza zeri davanti (640, 4755).
mode() { stat -c %a "$1"; }
