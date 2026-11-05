blocked() {
    for p in "$EX" "$EX/a" "$EX/a/b" "$EX/a/b/c" "$EX/a/b/c/d"; do
        runuser -u app -- test -x "$p" || { echo "$p"; return; }
    done
}
blocked
