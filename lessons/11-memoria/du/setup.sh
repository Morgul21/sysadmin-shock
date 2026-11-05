# Quattro cartelle in /dev/shm con dimensioni diverse tra loro, scelte a caso.
e=/dev/shm/esportazioni
mkdir -p "$EX"
set -- $(shuf -n 4 -e 2 5 8 12 18 25)
for d in clienti ordini fatture archivio; do
    mkdir -p "$e/$d"
    head -c "${1}M" /dev/zero > "$e/$d/export-$(word).dat"
    echo "indice" > "$e/$d/indice.txt"
    shift
done
