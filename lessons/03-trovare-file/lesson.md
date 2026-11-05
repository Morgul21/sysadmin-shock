Su un server non sai mai dove sta un file finché non lo cerchi: un log, una configurazione, un file
lasciato da qualcuno. `find` lo trova scendendo in tutte le sottocartelle; `which` trova i comandi.

## find: cercare scendendo nelle cartelle

La forma è `find` *cartella* *condizioni*: parte dalla cartella, scende in tutte le sottocartelle e
stampa il percorso di ogni file che soddisfa **tutte** le condizioni.

- `-name 'report*.txt'`: il nome; `*` vale qualunque sequenza di caratteri. Le virgolette servono,
  altrimenti `*` lo espande la shell prima che lo veda `find`. `-iname` ignora le maiuscole
- `-type f` solo i file, `-type d` solo le cartelle
- `-user luca`, `-group tecnici`: il proprietario o il gruppo
- `-perm -o+w`: i file con quel permesso (es. scrivibili da tutti)
- `-mmin -60`, `-mtime -1`: modificati negli ultimi 60 minuti o nell'ultimo giorno
- `-maxdepth 1`: non scendere nelle sottocartelle

Senza condizioni `find cartella` elenca tutto. Su tutto il disco (`find / …`) compaiono anche errori
`Permission denied` di cartelle speciali: come nasconderli è nella lezione 4.

## which: dove sta un comando

Quando scrivi un comando, la shell lo cerca come file eseguibile nelle cartelle della variabile `PATH`,
nell'ordine, e lancia il primo che trova. `echo $PATH` mostra l'elenco, separato da `:`.

`which comando` fa la stessa ricerca e stampa il percorso: serve a sapere **quale** programma parte
davvero, per esempio quando ne esistono due copie.

```prova
echo $PATH
which ls
which gestionale
find /srv/app -type f
find /etc -name '*.service'
find /srv -maxdepth 2 -user app
```
