Ogni file ha un **proprietario** (un utente), un **gruppo** e tre terne di permessi.
`ls -l` li mostra tutti in una riga:

```
-rwxr-x---  1 app  contabilita  1200 ott 24 09:10 run.sh
```

## La prima colonna

Sono dieci caratteri. Il primo è il tipo (`-` file, `d` cartella, `l` link), poi vengono tre terne:

- caratteri 2–4: il **proprietario** (`u`, *user*)
- caratteri 5–7: il **gruppo** (`g`)
- caratteri 8–10: gli **altri** (`o`, *others*), cioè chiunque non sia il proprietario né nel gruppo

Ogni terna è sempre nell'ordine `r` `w` `x`, e un `-` vuol dire che quel permesso manca.
Nell'esempio, `app` legge, scrive ed esegue; chi è nel gruppo `contabilita` legge ed esegue; gli altri niente.

## Cosa vogliono dire r, w, x su un file

- `r`: leggerne il contenuto (`cat`, `less`, un programma che lo apre)
- `w`: modificarlo
- `x`: eseguirlo come programma. Senza `x` uno script si legge ma non parte, e l'errore è `Permission denied`

Sulle cartelle le stesse lettere vogliono dire altro: è la lezione 8.

## Quale terna conta

Linux ne sceglie **una sola**, in quest'ordine:

1. sei il proprietario? Conta la terna del proprietario, e basta
2. sei nel gruppo del file? Conta quella del gruppo
3. altrimenti conta quella degli altri

Le terne non si sommano: se il file è tuo e la tua terna è `---`, non lo leggi, anche se gli altri sì.
L'eccezione è `root`, che salta questi controlli. Per questo da root non basta provare: va provato
come l'utente giusto, con `runuser -u app -- comando`, che esegue il comando come `app`.

## Gli strumenti

- `ls -l cartella` per tutti i file, `ls -l file` per uno solo
- `stat file` dice tutto di un file; `stat -c '%A %U:%G %n' file` solo permessi, proprietario e gruppo
- `id utente` dice in quali gruppi è un utente

Un clic su un comando lo esegue nel terminale:

```prova
ls -l /srv/app
stat /srv/app/run.sh
id app
runuser -u app -- cat /srv/app/run.sh
runuser -u app -- cat /etc/shadow
```
