expected=$(command -v saluta) || fail "il comando saluta non c'è più: riavvia l'esercizio"
expect_path "$expected"
pass "saluta è $expected: è il primo che la shell trova nel PATH"
