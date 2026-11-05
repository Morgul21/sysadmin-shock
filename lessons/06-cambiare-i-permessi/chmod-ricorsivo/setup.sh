# Cartelle e file con permessi diversi tra loro, quasi tutti aperti agli altri: un numero ottale
# unico per tutti non può andare bene.
c="$EX/cartella"
mkdir -p "$c/sotto-a" "$c/sotto-b"
chmod 755 "$EX"
for f in uno.txt sotto-a/due.txt sotto-a/tre.txt sotto-b/quattro.txt sotto-b/cinque.txt; do
    echo "file di prova" > "$c/$f"
done
chown -R app:app "$c"
for d in "$c" "$c/sotto-a" "$c/sotto-b"; do
    chmod "$(pick 755 775 751 705)" "$d"
done
for f in $(find "$c" -type f); do
    chmod "$(pick 644 664 604 654 640)" "$f"
done
# Almeno uno aperto agli altri anche se il caso li avesse chiusi tutti.
chmod 644 "$c/uno.txt"
mkdir -p "$STATE"
find "$c" -printf '%m %p\n' > "$STATE/cartella"
