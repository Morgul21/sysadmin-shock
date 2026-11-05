# Cinque script del proprietario app: tutti eseguibili da lui (con permessi diversi per gli altri),
# tranne uno a caso.
mkdir -p "$EX"
chmod 755 "$EX"
for name in backup.sh report.sh pulizia.sh sync.sh avvio.sh; do
    printf '#!/bin/sh\necho "%s eseguito"\n' "$name" > "$EX/$name"
    chown app:app "$EX/$name"
    chmod "$(pick 755 750 700 754)" "$EX/$name"
done
chmod "$(pick 644 640 600 655)" "$EX/$(pick backup.sh report.sh pulizia.sh sync.sh avvio.sh)"
