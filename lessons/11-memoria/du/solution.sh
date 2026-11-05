du -s /dev/shm/esportazioni/* | sort -n | tail -1 | awk '{print $2}'
