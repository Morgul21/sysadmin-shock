expected=$(ps -eo pid=,rss= --sort=-rss | head -1 | awk '{print $1}')
pgrep -f /opt/lavori/ | grep -qx "$expected" || fail "il processo più grande non è più uno dei lavori: riavvia l'esercizio"
expect_answer "$expected"
pass "il PID $expected ($(ps -o args= -p "$expected")) occupa $(( $(ps -o rss= -p "$expected") / 1024 )) MB"
