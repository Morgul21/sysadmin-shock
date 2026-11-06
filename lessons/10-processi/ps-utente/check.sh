expected=$(ps -u luca --no-headers | wc -l)
[ "$expected" -gt 0 ] || fail "luca non ha più processi: riavvia l'esercizio"
expect_answer "$expected"
pass "luca ha $expected processi: $(ps -u luca -o comm= | sort | uniq -c | awk '{printf "%s %s, ", $1, $2}' | sed 's/, $//')"
