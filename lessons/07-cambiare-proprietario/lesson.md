I permessi (lezioni 5 e 6) dicono cosa possono fare proprietario, gruppo e altri. Ma chi è il
proprietario, e qual è il gruppo? Si cambiano con `chown` e `chgrp`, e spesso il problema è proprio lì:
il permesso c'è, ma è dato all'utente sbagliato.

## Il caso tipico: un file lavorato da root

Quando `root` crea o ricrea un file (un editor che salva una copia nuova, un comando lanciato a mano),
il file nuovo appartiene a `root:root`. L'applicazione, che gira come un altro utente, non lo legge o
non lo scrive più, anche se i permessi sembrano gli stessi di prima. La soluzione giusta è restituire il
file al suo proprietario, non aprire i permessi a tutti.

## chown: cambiare proprietario (e gruppo)

- `chown anna file`: il proprietario diventa `anna`, il gruppo resta quello
- `chown anna:tecnici file`: proprietario `anna` e gruppo `tecnici` insieme
- `chown :tecnici file`: solo il gruppo (come `chgrp`)
- `chown -R app:app cartella`: la cartella e tutto quello che contiene

Solo `root` può cambiare il proprietario di un file: un utente normale non può "regalare" i suoi file.

## chgrp: cambiare solo il gruppo

`chgrp tecnici file` cambia il gruppo. Un utente normale può farlo solo sui propri file, e solo verso
un gruppo di cui fa parte.

## Chi c'è in un gruppo

- `id utente`: i gruppi di un utente
- `getent group tecnici`: i membri di un gruppo (l'ultimo campo, separati da virgole)

`chown` e `chgrp` non toccano i permessi: dopo, `ls -l` mostra le stesse lettere, con nomi diversi.

```prova
ls -l /srv/app
id app
getent group app
find /srv/app -user root
```
