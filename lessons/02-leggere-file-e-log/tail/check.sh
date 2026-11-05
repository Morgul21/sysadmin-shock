expected=$(tail -n 5 "$EX/app.log" | head -n 1 | sed 's/.*id=//')
expect_answer "$expected"
pass "la quintultima riga è: $(tail -n 5 "$EX/app.log" | head -n 1)"
