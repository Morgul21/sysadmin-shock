expected=$(ls -1 "$EX" | wc -l)
expect_answer "$expected"
pass "ls mostra $expected elementi: $(ls "$EX" | tr '\n' ' ')"
