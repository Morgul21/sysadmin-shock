groupadd contabilita
mkdir -p "$EX"
chmod 755 "$EX"
printf 'nome;netto\nGiulia;1850\nMarco;1720\n' > "$EX/stipendi.csv"
chown app:contabilita "$EX/stipendi.csv"
chmod "$(pick 644 666 604 600 664 777)" "$EX/stipendi.csv"
