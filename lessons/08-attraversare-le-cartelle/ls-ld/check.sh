expected=""
for d in alfa beta gamma; do
    if runuser -u app -- test -x "$EX/$d" && ! runuser -u app -- test -r "$EX/$d"; then
        expected="$expected$d"
    fi
done
case "$expected" in alfa|beta|gamma) ;; *) fail "le cartelle non sono più come all'inizio: riavvia l'esercizio" ;; esac
expect_answer "$expected"
pass "$expected è $(stat -c %A "$EX/$expected"): gli altri hanno la x (entrare) ma non la r (elencare)"
