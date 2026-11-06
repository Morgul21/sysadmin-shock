mkdir -p "$EX"
chmod 755 "$EX"
for name in uno.txt due.txt tre.txt; do
    echo "file di prova" > "$EX/$name"
done
echo "trovato" > "$EX/.$(pick segreto nascosto riservato privato)-$(rnd 100 999)"
