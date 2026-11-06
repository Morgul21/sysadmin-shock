expected=$(grep -c ERROR "$EX/app.log" || true)
expect_answer "$expected"
pass "$expected righe contengono ERROR (con grep -i sarebbero $(grep -ci error "$EX/app.log"): attenzione alle maiuscole)"
