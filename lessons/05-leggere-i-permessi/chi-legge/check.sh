# Il verdetto lo dà il kernel: lo stesso controllo che fa quando app apre il file.
if runuser -u app -- test -r "$EX/nota.txt"; then expected=si; else expected=no; fi
expect_answer "$expected"
[ "$expected" = si ] && can="può" || can="non può"
pass "app $can leggerlo: $(stat -c '%A %U:%G' "$EX/nota.txt") (id app: $(id app))"
