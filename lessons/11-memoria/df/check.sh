expected=$(df /dev/shm | awk 'NR == 2 {print $5}' | tr -d %)
ANSWER=$(printf '%s' "$ANSWER" | tr -d '% ')
expect_answer "$expected"
pass "/dev/shm è pieno al $expected%: $(df -h /dev/shm | awk 'NR == 2 {print $3 " usati su " $2}'), tutti in RAM"
