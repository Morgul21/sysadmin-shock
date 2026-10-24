# Funzioni condivise dai check: il runner le antepone a ogni check.sh.
# Un check stampa PASS/FAIL con il motivo ed esce con 0 (pass) o 1 (fail).
# set -e: un errore inatteso nel check è un FAIL, mai un PASS.
set -e

fail() { echo "FAIL: $*"; exit 1; }
pass() { echo "PASS: $*"; exit 0; }

# Il criterio di tutti gli scenari: l'app riparte come utente app.
app_starts() {
    # Non `gestionale`: è un file del server e chi ripara potrebbe cambiarlo (es. farlo girare da root).
    out=$(runuser -u app -- /srv/app/run.sh 2>&1) || fail "il gestionale non parte: $out"
}

# Correzione eccessiva: file o directory scrivibili da tutti (senza sticky bit).
no_world_writable() {
    found=$(find "$@" -xdev ! -type l -perm -o+w ! -perm -1000 2>/dev/null | head -5)
    [ -z "$found" ] || fail "scrivibili da tutti (correzione eccessiva): $found"
}

# Il codice dell'app è quello dell'immagine: "riparare" riscrivendo run.sh o cache.py non vale.
# APP_SHA256 lo antepone il runner, con gli hash calcolati sui file dell'host.
app_unchanged() {
    changed=$(echo "$APP_SHA256" | sha256sum -c 2>/dev/null | grep -v ': OK$' | cut -d: -f1)
    [ -z "$changed" ] || fail "il codice dell'app è stato modificato: $changed"
}

# Controlli comuni a ogni scenario: l'app (originale) parte e nessuno ha "riparato" aprendo tutto.
baseline() {
    app_unchanged
    app_starts
    no_world_writable /srv /etc /opt /var/log/app
}
