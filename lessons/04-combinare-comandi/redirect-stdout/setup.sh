mkdir -p "$EX/dati"
chmod 755 "$EX"
for name in $(shuf -n "$(rnd 5 9)" -e clienti.csv ordini.csv prodotti.csv fornitori.csv listino.pdf \
        magazzino.ods contratti.zip fatture.zip note.txt); do
    echo "file di prova" > "$EX/dati/$name"
done
