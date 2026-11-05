# saluta in una cartella del PATH scelta a caso, e una copia in /srv/esercizi, che non è nel PATH.
mkdir -p "$EX"
chmod 755 "$EX"
dir=$(pick /usr/local/bin /usr/local/sbin /usr/bin /usr/sbin)
printf '#!/bin/sh\necho "Ciao! Sono il comando saluta."\n' > "$dir/saluta"
chmod 755 "$dir/saluta"
cp "$dir/saluta" "$EX/saluta"
