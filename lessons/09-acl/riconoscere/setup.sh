# Cinque file uguali, uno solo con un'ACL.
mkdir -p "$EX"
chmod 755 "$EX"
files="note.txt piano.txt elenco.txt orari.txt contatti.txt"
for f in $files; do
    echo "file di prova" > "$EX/$f"
    chmod "$(pick 644 664 640)" "$EX/$f"
done
setfacl -m "u:app:$(pick r rw)" "$EX/$(pick $files)"
