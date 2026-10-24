baseline
[ -d /dev/shm ] || fail "/dev/shm è stato rimosso"
pass "la memoria condivisa è stata liberata"
