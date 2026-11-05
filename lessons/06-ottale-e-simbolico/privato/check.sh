open=$(find "$EX/privato" -perm /o=rwx -printf '%M %p\n' | head -5)
[ -z "$open" ] || fail "gli altri hanno ancora dei permessi: $open"
while read -r start path; do
    [ -e "$path" ] || fail "$path non c'è più"
    now=$(mode "$path")
    [ $(( 0$now & 0770 )) = $(( 0$start & 0770 )) ] \
        || fail "$path: sono cambiati anche i permessi di proprietario o gruppo ($start → $now)"
done < "$STATE/privato"
pass "gli altri non hanno più permessi su privato/, e proprietario e gruppo sono rimasti com'erano"
