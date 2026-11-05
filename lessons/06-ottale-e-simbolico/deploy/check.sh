f="$EX/deploy.sh"
start=$(saved deploy.mode)
now=$(mode "$f")
want=$(printf '%o' $(( 0$start | 0100 )))
[ "$now" != "$start" ] || fail "deploy.sh è ancora $(stat -c %A "$f")"
[ "$now" = "$want" ] || fail "deploy.sh è passato da $(saved deploy.symbolic) a $(stat -c %A "$f"): è cambiato anche altro oltre alla x del proprietario"
pass "deploy.sh è passato da $(saved deploy.symbolic) a $(stat -c %A "$f"): solo la x del proprietario"
