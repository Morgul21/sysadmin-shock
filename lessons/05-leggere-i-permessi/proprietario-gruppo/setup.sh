# Quattro file con proprietari e gruppi diversi; uno solo del gruppo tecnici.
# luca è nel gruppo tecnici e possiede un file di un altro gruppo: chi confonde le due colonne
# di `ls -l` sbaglia.
groupadd ufficio
groupadd tecnici
groupadd ospiti
useradd -M -N -g ufficio anna
useradd -M -N -g tecnici luca
mkdir -p "$EX"
chmod 755 "$EX"
files="a.txt b.txt c.txt d.txt"
target=$(pick $files)
decoy=$(pick $(echo "$files" | tr ' ' '\n' | grep -vx "$target"))
for f in $files; do
    echo "file di prova" > "$EX/$f"
    chown "$(pick anna app root):$(pick ufficio ospiti)" "$EX/$f"
    chmod 640 "$EX/$f"
done
chown "luca:$(pick ufficio ospiti)" "$EX/$decoy"
chown "$(pick anna app root):tecnici" "$EX/$target"
