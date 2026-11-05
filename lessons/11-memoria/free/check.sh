expected=$(free -m | awk '/^Mem:/ {print $2}')
expect_answer "$expected"
pass "free vede $expected MB: è la memoria della macchina, non il limite del container (esercizio successivo)"
