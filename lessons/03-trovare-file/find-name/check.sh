dir=$(find "$EX/archivio" -type f -name trovami.txt -printf '%h\n')
[ "$(printf '%s' "$dir" | grep -c .)" = 1 ] || fail "in $EX/archivio non c'è più un solo trovami.txt: riavvia l'esercizio"
expect_path "$dir" "$dir/trovami.txt"
pass "trovami.txt è in $dir"
