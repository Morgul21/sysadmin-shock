# Un sito di app con file e cartelle passati a root a caso, e permessi diversi da conservare.
s="$EX/sito"
mkdir -p "$s/css" "$s/img" "$s/pagine/archivio"
chmod 755 "$EX"
for f in index.html css/stile.css img/logo.png pagine/chi-siamo.html pagine/contatti.html pagine/archivio/2025.html; do
    echo "contenuto" > "$s/$f"
done
chown -R app:app "$s"
for p in $(find "$s"); do
    if [ -d "$p" ]; then chmod "$(pick 755 750)" "$p"; else chmod "$(pick 644 640 664)" "$p"; fi
done
for p in $(find "$s" -mindepth 1 | shuf -n "$(rnd 3 6)"); do
    chown "root:$(pick root app)" "$p"
done
chown root:root "$s/pagine"
mkdir -p "$STATE"
find "$s" -printf '%m %p\n' > "$STATE/sito"
