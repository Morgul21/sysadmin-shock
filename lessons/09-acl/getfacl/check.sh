expected=$(getfacl -p "$EX/progetto.txt" 2>/dev/null | sed -n 's/^user:luca:\([rwx-]*\).*/\1/p')
[ -n "$expected" ] || fail "nell'ACL non c'è più la voce di luca: riavvia l'esercizio"
expect_answer "$expected"
pass "luca ha $expected: è la riga user:luca: di getfacl"
