# File di più utenti, in più sottocartelle; luca possiede anche delle cartelle, che non vanno contate.
useradd -M -N anna
useradd -M -N luca
c="$EX/condivisa"
mkdir -p "$c/progetti/vecchi" "$c/documenti" "$c/scambio"
chmod 755 "$EX"
for dir in "$c" "$c/progetti" "$c/progetti/vecchi" "$c/documenti" "$c/scambio"; do
    for i in $(seq "$(rnd 3 6)"); do
        f="$dir/file-$i.txt"
        echo "file di prova" > "$f"
        chown "$(pick app root anna luca)" "$f"
    done
done
chown luca "$c/scambio" "$c/progetti/vecchi" "$c/documenti/file-1.txt"
