# Processi di tre utenti, con nomi diversi (copie di sleep): luca ne ha un numero a caso.
useradd -M -N luca
useradd -M -N anna
for name in sincronizza indicizza backup-notturno controlla-posta; do
    cp /bin/sleep "/usr/local/bin/$name"
done
programs="sincronizza indicizza backup-notturno controlla-posta"
for user in luca anna app; do
    for _ in $(seq "$(rnd 1 5)"); do
        setsid nohup runuser -u "$user" -- "$(pick $programs)" 100000 < /dev/null > /dev/null 2>&1 &
    done
done
sleep 1
