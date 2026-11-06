f="$EX/dati.txt"
[ "$(stat -c %U:%G "$f")" = app:ufficio ] || fail "proprietario e gruppo dovevano restare app:ufficio, ora sono $(stat -c %U:%G "$f")"
[ "$(mode "$f")" = 640 ] || fail "dati.txt è $(stat -c %A "$f"): non è ancora rw-r-----"
pass "dati.txt è $(stat -c %A "$f") (640)"
