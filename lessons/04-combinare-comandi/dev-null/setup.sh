# Centinaia di righe "codice: …" sullo stderr e una sola sullo stdout, in un punto a caso:
# a schermo sono identiche, solo buttando via lo stderr resta quella giusta.
mkdir -p "$EX"
chmod 755 "$EX"
awk -v n="$(rnd 200 400)" -v at="$(rnd 50 150)" -v code="$(word)" 'BEGIN {
    srand()
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    print "#!/bin/sh"
    for (i = 1; i <= n; i++) {
        if (i == at) { printf "echo \"codice: %s\"\n", code; continue }
        old = ""
        for (j = 0; j < 6; j++) old = old substr(chars, int(rand() * 36) + 1, 1)
        if (i % 3 == 0) printf "echo \"codice: %s\" >&2\n", old
        else printf "echo \"avviso: controllo %d lento\" >&2\n", i
    }
}' > "$EX/rumoroso.sh"
chmod 755 "$EX/rumoroso.sh"
