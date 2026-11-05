[ -z "$(pgrep -f /opt/lavori/bloccato.py || true)" ] \
    || fail "bloccato.py gira ancora (PID $(pgrep -f /opt/lavori/bloccato.py)): ignora TERM, serve un altro segnale"
[ -n "$(pgrep -f /opt/lavori/report.py || true)" ] || fail "report.py doveva continuare a girare"
pass "bloccato.py è fermo: KILL non si può ignorare. report.py gira ancora"
