baseline
[ "$(stat -c %U /srv/app/data)" = app ] || fail "/srv/app/data deve restare dell'utente app"
pass "il file di stato è di nuovo scrivibile dall'app"
