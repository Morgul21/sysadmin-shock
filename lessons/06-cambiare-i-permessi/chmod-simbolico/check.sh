f="$EX/script.sh"
start=$(saved script.mode)
now=$(mode "$f")
want=$(printf '%o' $(( 0$start | 0100 )))
[ "$now" != "$start" ] || fail "script.sh è ancora $(stat -c %A "$f")"
[ "$now" = "$want" ] || fail "script.sh è passato da $(saved script.symbolic) a $(stat -c %A "$f"): è cambiato anche altro oltre alla x del proprietario"
pass "script.sh è passato da $(saved script.symbolic) a $(stat -c %A "$f"): solo la x del proprietario"
