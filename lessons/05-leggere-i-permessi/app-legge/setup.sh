# Un caso a caso tra quelli in cui l'intuizione sbaglia: app proprietario senza permessi suoi,
# app nel gruppo con la terna del gruppo vuota, ...
mkdir -p "$EX"
chmod 755 "$EX"
echo "Promemoria: inventario venerdì" > "$EX/nota.txt"
case=$(pick "app:app 044" "app:app 404" "app:root 400" "root:app 640" "root:app 604" "root:root 604" "root:root 640")
chown "${case% *}" "$EX/nota.txt"
chmod "${case#* }" "$EX/nota.txt"
