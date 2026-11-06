# Tre cartelle di root: una sola con la x senza la r per gli altri (751), le altre due no.
mkdir -p "$EX"
chmod 755 "$EX"
modes="751 $(shuf -n 2 -e 754 755 750 | tr '\n' ' ')"
for d in alfa beta gamma; do
    mkdir "$EX/$d"
    echo "contenuto di $d" > "$EX/$d/leggimi.txt"
    chmod 644 "$EX/$d/leggimi.txt"
done
set -- $(echo $modes | tr ' ' '\n' | shuf)
chmod "$1" "$EX/alfa"
chmod "$2" "$EX/beta"
chmod "$3" "$EX/gamma"
