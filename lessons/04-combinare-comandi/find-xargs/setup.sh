# File .tmp sparsi tra file da tenere; uno con uno spazio nel nome (xargs senza -0 lo sbaglia)
# e due trappole che non finiscono in .tmp.
p="$EX/progetto"
mkdir -p "$p/src/lib" "$p/docs" "$p/build/cache"
chmod 755 "$EX"
for dir in "$p" "$p/src" "$p/src/lib" "$p/docs" "$p/build" "$p/build/cache"; do
    for f in $(shuf -n "$(rnd 1 3)" -e main.py utils.py readme.md note.txt config.ini dati.csv); do
        echo "da tenere" > "$dir/$f"
    done
    for i in $(seq "$(rnd 1 4)"); do
        echo "temporaneo" > "$dir/lavoro-$i.tmp"
    done
done
echo "temporaneo" > "$p/docs/file con spazio.tmp"
echo "da tenere" > "$p/src/nota.tmp.txt"
echo "da tenere" > "$p/build/tmp-vecchio.txt"
mkdir -p "$STATE"
find "$p" -type f ! -name '*.tmp' > "$STATE/da-tenere"
