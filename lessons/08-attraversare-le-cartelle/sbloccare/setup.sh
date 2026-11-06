# Il file è leggibile da tutti, ma una cartella a caso del percorso non è attraversabile dagli altri.
mkdir -p "$EX/a/b/c/d"
chmod 755 "$EX" "$EX/a" "$EX/a/b" "$EX/a/b/c" "$EX/a/b/c/d"
echo "dati di prova" > "$EX/a/b/c/d/dati.txt"
chmod 644 "$EX/a/b/c/d/dati.txt"
chmod "$(pick 750 700 754)" "$(pick "$EX/a" "$EX/a/b" "$EX/a/b/c" "$EX/a/b/c/d")"
mkdir -p "$STATE"
find "$EX" -type d -printf "%m %p\n" > "$STATE/cartelle"
