# Quattro documenti con proprietari e gruppi diversi; uno solo del gruppo magazzino.
# Marco ha magazzino come gruppo principale e possiede un file di un altro gruppo: chi confonde
# le due colonne di `ls -l` sbaglia.
groupadd contabilita
groupadd magazzino
groupadd direzione
useradd -M -N -g contabilita giulia
useradd -M -N -g magazzino marco
mkdir -p "$EX/documenti"
chmod 755 "$EX" "$EX/documenti"
files="fatture.pdf inventario.ods ordini.csv turni.txt"
target=$(pick $files)
decoy=$(pick $(echo "$files" | tr ' ' '\n' | grep -vx "$target"))
for f in $files; do
    echo "documento di prova" > "$EX/documenti/$f"
    chown "$(pick giulia app root):$(pick contabilita direzione)" "$EX/documenti/$f"
    chmod 640 "$EX/documenti/$f"
done
chown "marco:$(pick contabilita direzione)" "$EX/documenti/$decoy"
chown "$(pick giulia app root):magazzino" "$EX/documenti/$target"
