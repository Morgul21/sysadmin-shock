f="$EX/config.ini"
[ "$(stat -c %U:%G "$f")" = anna:tecnici ] || fail "config.ini è di $(stat -c %U:%G "$f"), non di anna:tecnici"
[ "$(mode "$f")" = "$(saved config.mode)" ] || fail "i permessi sono cambiati: ora $(stat -c %A "$f")"
pass "config.ini è di anna:tecnici, con i permessi di prima ($(stat -c %A "$f"))"
