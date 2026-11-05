expected=$(find "$EX" -maxdepth 1 -type f -name '.*' -printf '%f\n')
[ "$(printf '%s' "$expected" | grep -c .)" = 1 ] || fail "in $EX non c'è più un solo file nascosto: riavvia l'esercizio"
expect_answer "$expected"
pass "$expected comincia con un punto: ls lo nasconde, ls -a lo mostra"
