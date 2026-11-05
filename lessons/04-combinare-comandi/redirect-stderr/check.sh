out="$EX/output.txt"
err="$EX/errori.txt"
[ -f "$out" ] || fail "$out non c'è"
[ -f "$err" ] || fail "$err non c'è"
[ "$(cat "$out")" = "$("$EX/controlla.sh" 2>/dev/null)" ] \
    || fail "output.txt non contiene esattamente lo stdout di controlla.sh (ci sono errori dentro? manca qualcosa?)"
[ "$(cat "$err")" = "$("$EX/controlla.sh" 2>&1 >/dev/null)" ] \
    || fail "errori.txt non contiene esattamente lo stderr di controlla.sh"
pass "stdout in output.txt ($(wc -l < "$out") righe), stderr in errori.txt ($(wc -l < "$err") righe)"
