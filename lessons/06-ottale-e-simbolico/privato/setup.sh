# Cartelle e file con permessi diversi tra loro, quasi tutti aperti agli altri: un numero ottale
# unico per tutti non può andare bene.
mkdir -p "$EX/privato/contratti" "$EX/privato/buste-paga"
chmod 755 "$EX"
for f in contratti/fornitore-a.pdf contratti/fornitore-b.pdf buste-paga/ottobre.pdf buste-paga/novembre.pdf note.txt; do
    echo "riservato" > "$EX/privato/$f"
done
chown -R app:app "$EX/privato"
for d in "$EX/privato" "$EX/privato/contratti" "$EX/privato/buste-paga"; do
    chmod "$(pick 755 775 751 705)" "$d"
done
for f in $(find "$EX/privato" -type f); do
    chmod "$(pick 644 664 604 654 640)" "$f"
done
# Almeno uno aperto agli altri anche se il caso li avesse chiusi tutti.
chmod 644 "$EX/privato/note.txt"
mkdir -p "$STATE"
find "$EX/privato" -printf '%m %p\n' > "$STATE/privato"
