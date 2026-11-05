echo $(( $(cat /sys/fs/cgroup/memory.max) / 1024 / 1024 ))
