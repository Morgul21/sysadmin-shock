expected=$(find "$EX/documenti" -maxdepth 1 -type f -group magazzino -printf '%f\n')
[ "$(printf '%s' "$expected" | grep -c .)" = 1 ] \
    || fail "in $EX/documenti non c'è più uno e un solo file del gruppo magazzino: riavvia l'esercizio"
expect_answer "$expected"
pass "$expected appartiene a $(stat -c %U:%G "$EX/documenti/$expected"): il gruppo è il secondo nome"
