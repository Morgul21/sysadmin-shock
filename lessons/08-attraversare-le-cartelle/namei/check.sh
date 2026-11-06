blocked() {
    for p in "$EX" "$EX/a" "$EX/a/b" "$EX/a/b/c" "$EX/a/b/c/d"; do
        runuser -u app -- test -x "$p" || { echo "$p"; return; }
    done
}
expected=$(blocked)
[ -n "$expected" ] || fail "app ormai attraversa tutto il percorso: hai cambiato i permessi? Riavvia l'esercizio"
expect_path "$expected"
pass "$expected è $(stat -c %A "$expected"): gli altri non hanno la x, quindi app non può attraversarla"
