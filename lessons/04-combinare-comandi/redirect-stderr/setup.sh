# controlla.sh: controlli riusciti sullo stdout, errori sullo stderr, mescolati e diversi a ogni avvio.
mkdir -p "$EX"
chmod 755 "$EX"
s="$EX/controlla.sh"
printf '#!/bin/sh\n' > "$s"
for name in $(shuf -e web database posta backup dns stampa vpn cache code ldap); do
    if [ "$(rnd 1 3)" = 1 ]; then
        echo "echo \"ERRORE: $name non risponde\" >&2" >> "$s"
    else
        echo "echo \"OK: $name\"" >> "$s"
    fi
done
echo 'echo "ERRORE: controllo finale non riuscito" >&2' >> "$s"
echo 'echo "OK: controlli finiti"' >> "$s"
chmod 755 "$s"
