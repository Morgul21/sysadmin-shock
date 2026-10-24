baseline
[ "$(stat -c %U /srv)" = root ] || fail "/srv deve restare di root"
pass "/srv è di nuovo attraversabile"
