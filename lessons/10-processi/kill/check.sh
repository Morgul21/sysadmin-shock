[ -z "$(pgrep -f /opt/lavori/esporta.py || true)" ] || fail "esporta.py gira ancora (PID $(pgrep -f /opt/lavori/esporta.py))"
others=$(pgrep -cf '/opt/lavori/(report|indicizza)\.py' || true)
[ "$others" = 2 ] || fail "dovevano restare in esecuzione report.py e indicizza.py: ne girano $others"
pass "esporta.py è fermo, gli altri due lavori girano ancora"
