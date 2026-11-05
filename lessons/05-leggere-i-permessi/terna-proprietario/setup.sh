# Cinque file del proprietario app, tutti eseguibili da lui (con permessi diversi per gruppo e altri),
# tranne uno a caso. 655 è la trappola: gli altri possono eseguirlo, il proprietario no.
mkdir -p "$EX"
chmod 755 "$EX"
files="uno.sh due.sh tre.sh quattro.sh cinque.sh"
for name in $files; do
    printf '#!/bin/sh\necho "%s eseguito"\n' "$name" > "$EX/$name"
    chown app:app "$EX/$name"
    chmod "$(pick 755 750 700 754)" "$EX/$name"
done
chmod "$(pick 644 640 600 655)" "$EX/$(pick $files)"
