# Un numero a caso di file e cartelle, più un file nascosto che ls non conta.
mkdir -p "$EX"
chmod 755 "$EX"
for name in $(shuf -n "$(rnd 4 9)" -e note.txt foto.jpg dati.csv lista.txt report.pdf script.sh bozza.md \
        appunti.txt elenco.csv copia.bak); do
    echo "file di prova" > "$EX/$name"
done
for name in $(shuf -n "$(rnd 1 4)" -e archivio vecchi documenti immagini backup); do
    mkdir "$EX/$name"
done
touch "$EX/.impostazioni"
