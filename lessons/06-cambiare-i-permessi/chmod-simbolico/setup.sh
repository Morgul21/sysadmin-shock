# Permessi di partenza diversi a ogni avvio, nessuno con la x: la risposta non è un numero da ricordare.
mkdir -p "$EX"
chmod 755 "$EX"
printf '#!/bin/sh\necho "script eseguito"\n' > "$EX/script.sh"
chown app:app "$EX/script.sh"
chmod "$(pick 640 644 600 664 604)" "$EX/script.sh"
save script.mode "$(mode "$EX/script.sh")"
save script.symbolic "$(stat -c %A "$EX/script.sh")"
