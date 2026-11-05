s="$EX/sito"
wrong=$(find "$s" \( ! -user app -o ! -group app \) -printf '%u:%g %p\n' | head -5)
[ -z "$wrong" ] || fail "non è ancora tutto di app:app: $wrong"
while read -r start path; do
    [ -e "$path" ] || fail "$path non c'è più"
    [ "$(mode "$path")" = "$start" ] || fail "$path: i permessi sono cambiati ($start → $(mode "$path"))"
done < "$STATE/sito"
pass "tutto sito/ è di app:app, con i permessi di prima"
