expected=$(find "$EX" -maxdepth 1 -type f ! -perm -u+x -printf '%f\n')
[ "$(printf '%s' "$expected" | grep -c .)" = 1 ] \
    || fail "in $EX non c'è più uno e un solo file senza la x del proprietario: hai cambiato i permessi? Riavvia l'esercizio"
expect_answer "$expected"
pass "$expected è $(stat -c %A "$EX/$expected"): la terna del proprietario non ha la x"
