# Una cartella per anno e una per mese, qualche file qua e là, trovami.txt in una sola a caso.
# Due trappole per chi cerca con un * di troppo: vecchio-trovami.txt e trovami.txt.bak.
a="$EX/archivio"
for y in 2021 2022 2023 2024 2025; do
    for m in 01 02 03 04 05 06 07 08 09 10 11 12; do
        mkdir -p "$a/$y/$m"
        for f in $(shuf -n "$(rnd 0 3)" -e report.txt note.txt fattura.pdf foto.jpg); do
            echo "file di prova" > "$a/$y/$m/$f"
        done
    done
done
chmod 755 "$EX"
echo "eccomi" > "$a/$(pick 2021 2022 2023 2024 2025)/$(pick 01 02 03 04 05 06 07 08 09 10 11 12)/trovami.txt"
for decoy in vecchio-trovami.txt trovami.txt.bak; do
    dir="$a/$(pick 2021 2022 2023 2024 2025)/$(pick 01 02 03 04 05 06 07 08 09 10 11 12)"
    [ -e "$dir/trovami.txt" ] || echo "non sono io" > "$dir/$decoy"
done
