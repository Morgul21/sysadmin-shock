# Un log di centinaia di righe con id a caso e un numero a caso di ERROR (uguale per tail e grep).
# Alcune righe WARN contengono "error" in minuscolo: grep ERROR non le conta, grep -i sì.
mkdir -p "$EX"
chmod 755 "$EX"
awk -v n="$(rnd 300 600)" -v errors="$(rnd 8 30)" 'BEGIN {
    srand()
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    for (i = 1; i <= n; i++) {
        id = ""
        for (j = 0; j < 6; j++) id = id substr(chars, int(rand() * 36) + 1, 1)
        r = rand()
        if (r < errors / n) line = "ERROR richiesta fallita"
        else if (r < errors / n + 0.05) line = "WARN ritento dopo un error di rete"
        else if (r < errors / n + 0.15) line = "WARN risposta lenta"
        else line = "INFO richiesta servita"
        printf "2026-11-05 %02d:%02d:%02d %s id=%s\n", 8 + int(i / 3600), int(i / 60) % 60, i % 60, line, id
    }
}' > "$EX/app.log"
