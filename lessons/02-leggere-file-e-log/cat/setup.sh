mkdir -p "$EX"
chmod 755 "$EX"
cat > "$EX/messaggio.txt" <<MSG
Ciao,
questo file serve per l'esercizio su cat.
Il codice è: $(word)
Buon lavoro!
MSG
