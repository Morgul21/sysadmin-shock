expected=$(find "$EX/log" -maxdepth 1 -type f -name '*.log' | wc -l)
expect_answer "$expected"
pass "i file .log sono $expected (su $(ls "$EX/log" | wc -l) file in tutto)"
