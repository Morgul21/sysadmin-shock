# luca è nel gruppo tecnici; il file ha già i permessi giusti per il gruppo, ma il gruppo sbagliato.
groupadd tecnici
groupadd ospiti
useradd -M -N -G tecnici luca
mkdir -p "$EX"
chmod 755 "$EX"
printf 'giorno;turno\nlunedì;mattina\n' > "$EX/turni.csv"
owner=$(pick app root)
chown "$owner:$(pick ospiti root)" "$EX/turni.csv"
chmod 640 "$EX/turni.csv"
save turni.owner "$owner"
