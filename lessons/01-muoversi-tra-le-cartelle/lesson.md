## L'albero delle cartelle

In Linux tutto sta in un unico albero di **cartelle** (directory), che parte dalla radice `/`.
Non ci sono `C:` o `D:`: anche un disco in più diventa una cartella dell'albero.

Alcune cartelle si trovano su ogni server:

- `/etc`: la configurazione del sistema e dei servizi
- `/var/log`: i log
- `/home`: le cartelle degli utenti (qui `root` ha la sua in `/root`)
- `/usr/bin`, `/usr/local/bin`: i programmi
- `/srv`: i dati che il server offre, come le applicazioni (qui `/srv/app`)
- `/tmp`: file temporanei

## Percorsi assoluti e relativi

Un **percorso** dice dove si trova un file. Quello **assoluto** parte dalla radice:
`/srv/esercizi/uno.txt` è il file `uno.txt`, nella cartella `esercizi`, nella cartella `srv`.

Quello **relativo** parte dalla cartella in cui sei: se sei in `/srv`, `esercizi/uno.txt` è lo stesso file.
Due nomi speciali valgono in ogni cartella: `.` è la cartella stessa, `..` quella che la contiene.

## pwd e cd: dove sono, dove vado

- `pwd` (*print working directory*) dice in quale cartella sei
- `cd cartella` ti sposta in una cartella; `cd ..` sale di un livello; `cd` da solo torna alla tua cartella personale; `cd -` torna dove eri prima

Il Tab completa nomi di cartelle e file: scrivi l'inizio e premi Tab.

## ls: cosa c'è in una cartella

- `ls` elenca la cartella in cui sei, `ls cartella` un'altra
- `ls -l` una riga per elemento, con permessi, proprietario, dimensione e data (lezione 5)
- `ls -a` mostra anche i file **nascosti**, quelli il cui nome comincia con un punto (es. `.bashrc`)
- `ls -R` scende anche nelle sottocartelle

Le opzioni si combinano: `ls -la` è `-l` più `-a`.

## mkdir e touch: creare

- `mkdir cartella` crea una cartella; con `-p` crea anche le cartelle intermedie che mancano
- `touch file` crea un file vuoto (se esiste già, ne aggiorna solo la data)

Un clic su un comando lo esegue nel terminale:

```prova
pwd
ls /
cd /srv
pwd
ls -l
ls -la /root
cd
```
