f="$EX/a/b/c/d/dati.txt"
runuser -u app -- cat "$f" > /dev/null 2>&1 || fail "app non riesce ancora a leggere $f: guarda con namei -l"
[ "$(mode "$f")" = 644 ] || fail "i permessi del file sono cambiati: il problema non era il file"
while read -r start path; do
    now=$(mode "$path")
    [ "$now" = "$start" ] && continue
    [ $(( 0$now )) = $(( 0$start | 01 )) ] \
        || fail "$path è passata da $start a $now: serviva solo la x per gli altri"
done < "$STATE/cartelle"
pass "app legge dati.txt, e l'unica modifica è la x per gli altri sulla cartella che bloccava"
