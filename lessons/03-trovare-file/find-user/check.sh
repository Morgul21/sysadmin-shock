expected=$(find "$EX/condivisa" -type f -user luca | wc -l)
expect_answer "$expected"
pass "luca possiede $expected file (più $(find "$EX/condivisa" -type d -user luca | wc -l) cartelle, che non contano)"
