f="$EX/stipendi.csv"
[ "$(stat -c %U:%G "$f")" = app:contabilita ] || fail "proprietario e gruppo dovevano restare app:contabilita, ora sono $(stat -c %U:%G "$f")"
[ "$(mode "$f")" = 640 ] || fail "stipendi.csv è $(stat -c %A "$f"): non è ancora come chiede l'esercizio"
pass "stipendi.csv è $(stat -c %A "$f") (640)"
