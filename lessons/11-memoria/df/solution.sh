df /dev/shm | awk 'NR == 2 {print $5}' | tr -d %
