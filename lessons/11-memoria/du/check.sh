expected=$(du -s /dev/shm/esportazioni/* | sort -n | tail -1 | awk '{print $2}')
expected=${expected##*/}
[ -n "$expected" ] || fail "/dev/shm/esportazioni è vuota: riavvia l'esercizio"
expect_answer "$expected"
pass "la più grande è $expected: $(du -sh "/dev/shm/esportazioni/$expected" | cut -f1)"
