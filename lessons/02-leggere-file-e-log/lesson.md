Su un server quasi tutto è un file di testo: la configurazione in `/etc`, i log in `/var/log`, gli
script di avvio. Leggerli bene è metà del lavoro.

## cat: tutto il file

`cat file` stampa tutto il contenuto del file nel terminale. Va bene per i file corti; per uno di
mille righe vedresti solo la fine, perché il resto scorre via.

## less: sfogliare un file lungo

`less file` apre il file una pagina alla volta:

- frecce, `Spazio` e `b` per scorrere avanti e indietro
- `/parola` cerca la parola, `n` va alla successiva
- `G` va in fondo, `g` torna all'inizio
- `q` esce

## head e tail: l'inizio e la fine

- `head file` stampa le prime 10 righe, `head -n 3 file` le prime 3
- `tail file` stampa le ultime 10 righe, `tail -n 20 file` le ultime 20

Nei log gli eventi nuovi sono in fondo, quindi `tail` è il primo comando da lanciare quando qualcosa
non va. `tail -f file` resta in ascolto e stampa le righe nuove man mano che arrivano: si esce con `Ctrl+C`.

## grep: solo le righe che contengono una parola

`grep parola file` stampa solo le righe che contengono la parola. Le opzioni più utili:

- `-i` ignora maiuscole e minuscole
- `-n` scrive il numero di ogni riga
- `-c` invece delle righe scrive quante sono
- `-v` al contrario: le righe che **non** contengono la parola
- `-r parola cartella` cerca in tutti i file di una cartella

Se la parola contiene spazi o caratteri speciali, va tra virgolette: `grep 'non trovato' file`.

```prova
cat /etc/hostname
head -n 5 /etc/passwd
tail -n 3 /var/log/app/app.log
grep app /etc/passwd
grep -n -i error /var/log/app/app.log
```
