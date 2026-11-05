expected=$(sed -n 's/^Il codice è: //p' "$EX/messaggio.txt")
[ -n "$expected" ] || fail "messaggio.txt è stato modificato: riavvia l'esercizio"
expect_answer "$expected"
pass "il codice è $expected"
