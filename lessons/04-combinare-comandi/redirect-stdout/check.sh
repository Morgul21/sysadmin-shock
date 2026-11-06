f="$EX/elenco.txt"
[ -f "$f" ] || fail "$f non c'è: lo stdout di ls non è finito in un file con quel nome"
[ -s "$f" ] || fail "$f è vuoto"
for name in $(ls "$EX/dati"); do
    grep -qF "$name" "$f" || fail "in elenco.txt manca $name: è proprio l'output di ls $EX/dati?"
done
pass "elenco.txt contiene l'elenco di $EX/dati ($(wc -l < "$f") righe)"
