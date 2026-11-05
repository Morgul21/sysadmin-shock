limit=$(cat /sys/fs/cgroup/memory.max)
[ "$limit" != max ] || fail "questo container non ha un limite di memoria"
expected=$(( limit / 1024 / 1024 ))
# 256, 256m, 256 MB e 256MiB vanno tutti bene.
ANSWER=$(answer | sed 's/[[:space:]]*\(mib\|mb\|m\)$//')
expect_answer "$expected"
pass "il limite è $limit byte, cioè $expected MB: molto meno dei $(free -m | awk '/^Mem:/ {print $2}') MB che mostra free"
