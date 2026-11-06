# Tre utenti con permessi diversi nell'ACL, scelti a caso.
for u in anna luca marco; do useradd -M -N "$u"; done
mkdir -p "$EX"
chmod 755 "$EX"
echo "progetto di prova" > "$EX/progetto.txt"
chmod 640 "$EX/progetto.txt"
setfacl -m "u:anna:$(pick r rw rx rwx),u:luca:$(pick r rw rx rwx 0),u:marco:$(pick r rw rx rwx)" "$EX/progetto.txt"
