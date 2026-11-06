# Un file temporaneo di dimensione a caso in /dev/shm: occupa RAM.
mkdir -p "$EX"
head -c "$(rnd 20 90)M" /dev/zero > "/dev/shm/cache-$(word).tmp"
