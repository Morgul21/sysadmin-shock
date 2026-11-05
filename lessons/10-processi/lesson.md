Un **processo** è un programma in esecuzione. Ognuno ha un numero, il **PID**, un utente con cui gira,
e occupa CPU e memoria. Quando un server rallenta o finisce la memoria, la prima domanda è: quale
processo, di chi, quanto occupa?

## ps: la fotografia dei processi

`ps aux` elenca tutti i processi, uno per riga. Le colonne che contano:

- `USER`: l'utente con cui gira
- `PID`: il numero del processo, quello che serve per fermarlo
- `%CPU`, `%MEM`: quanta CPU e quanta memoria usa, in percentuale
- `RSS`: la memoria vera che occupa, in kilobyte
- `COMMAND`: il comando, con i suoi argomenti

Varianti utili:

- `ps -u luca`: solo i processi di un utente
- `ps aux --sort=-rss | head`: i processi che occupano più memoria, in cima
- `pgrep -af nome`: PID e comando dei processi che contengono `nome`

`top` è la versione che si aggiorna da sola: `M` ordina per memoria, `P` per CPU, `q` esce.

## kill: mandare un segnale

`kill` non uccide per forza: manda un **segnale** a un processo.

- `kill PID` manda `TERM` (15): "per favore termina". Il programma può chiudere bene (salvare,
  rilasciare file), ma può anche ignorarlo
- `kill -9 PID` manda `KILL` (9): il kernel ferma il processo subito, senza chiedergli niente. Va
  usato quando `TERM` non basta: il programma non ha modo di chiudere bene
- `kill -l` elenca tutti i segnali

`pkill -f testo` manda il segnale a **tutti** i processi il cui comando contiene `testo`: comodo, ma
è facile prenderne più del previsto. Prima guarda con `pgrep -af testo` cosa colpiresti.

## Il processo numero 1

In un container il processo 1 è quello che lo tiene in vita (qui `sleep infinity`). Se lo fermi, il
container si spegne con tutto quello che c'è dentro: non è mai il processo giusto da fermare.

```prova
ps aux
ps -u root
ps aux --sort=-rss | head -5
pgrep -af sleep
kill -l
```
