# Più di cento file: un numero a caso di .log, gli altri con nomi simili che non finiscono in .log.
d="$EX/log"
mkdir -p "$d"
chmod 755 "$EX"
for i in $(seq "$(rnd 60 110)"); do : > "$d/servizio-$i.log"; done
for i in $(seq "$(rnd 20 50)"); do : > "$d/servizio-$i.log.gz"; done
for i in $(seq "$(rnd 5 15)"); do : > "$d/log-vecchio-$i.txt"; done
