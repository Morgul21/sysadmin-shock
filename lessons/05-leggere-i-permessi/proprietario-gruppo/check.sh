expected=$(find "$EX" -maxdepth 1 -type f -group tecnici -printf '%f\n')
[ "$(printf '%s' "$expected" | grep -c .)" = 1 ] \
    || fail "in $EX non c'è più uno e un solo file del gruppo tecnici: riavvia l'esercizio"
expect_answer "$expected"
pass "$expected appartiene a $(stat -c %U:%G "$EX/$expected"): il gruppo è il secondo nome"
