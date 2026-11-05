left=$(find "$EX/progetto" -type f -name '*.tmp' | head -5)
[ -z "$left" ] || fail "ci sono ancora file .tmp: $left"
while read -r keep; do
    [ -f "$keep" ] || fail "$keep è sparito, ma non era un .tmp"
done < "$STATE/da-tenere"
pass "tutti i .tmp sono stati cancellati, e i $(wc -l < "$STATE/da-tenere") file da tenere ci sono ancora"
