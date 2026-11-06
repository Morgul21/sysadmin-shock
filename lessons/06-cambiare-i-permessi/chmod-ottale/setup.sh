groupadd ufficio
mkdir -p "$EX"
chmod 755 "$EX"
printf 'riga 1\nriga 2\n' > "$EX/dati.txt"
chown app:ufficio "$EX/dati.txt"
chmod "$(pick 644 666 604 600 664 777)" "$EX/dati.txt"
