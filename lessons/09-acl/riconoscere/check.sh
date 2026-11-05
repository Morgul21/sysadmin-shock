expected=""
for f in "$EX"/*; do
    [ -n "$(getfacl --skip-base -p "$f" 2>/dev/null)" ] && expected="$expected${f##*/}"
done
[ -n "$expected" ] || fail "nessun file ha più un'ACL: riavvia l'esercizio"
expect_answer "$expected"
pass "$expected è $(ls -l "$EX/$expected" | cut -d' ' -f1): il + dice che c'è un'ACL"
