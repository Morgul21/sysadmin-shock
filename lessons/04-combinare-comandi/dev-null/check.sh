expected=$("$EX/rumoroso.sh" 2>/dev/null | sed -n 's/^codice: //p')
[ -n "$expected" ] || fail "rumoroso.sh non stampa più il codice: riavvia l'esercizio"
expect_answer "$expected"
pass "il codice sullo stdout è $expected; sullo stderr ce n'erano altri $("$EX/rumoroso.sh" 2>&1 >/dev/null | grep -c '^codice:')"
