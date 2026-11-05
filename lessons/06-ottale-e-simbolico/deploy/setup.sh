# Permessi di partenza diversi a ogni avvio: la risposta non è un numero da ricordare.
mkdir -p "$EX"
chmod 755 "$EX"
printf '#!/bin/sh\necho "deploy completato"\n' > "$EX/deploy.sh"
chown app:app "$EX/deploy.sh"
chmod "$(pick 640 644 600 664 604)" "$EX/deploy.sh"
save deploy.mode "$(mode "$EX/deploy.sh")"
save deploy.symbolic "$(stat -c %A "$EX/deploy.sh")"
