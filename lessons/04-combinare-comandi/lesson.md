I comandi Linux fanno una cosa sola, ma si collegano tra loro. Per farlo bisogna sapere dove
leggono e dove scrivono.

## stdin, stdout, stderr

Ogni comando ha tre flussi, ognuno con un numero:

- **stdin** (0): da dove legge l'input. Di solito la tastiera
- **stdout** (1): dove scrive il risultato. Di solito il terminale
- **stderr** (2): dove scrive errori e avvisi. Anche lui il terminale

Nel terminale stdout e stderr si vedono mescolati, ma sono due flussi separati: si possono mandare in
posti diversi. Per esempio, `ls /srv /non-esiste` scrive l'elenco di `/srv` sullo stdout e
`No such file or directory` sullo stderr.

## Redirect: mandare un flusso in un file

- `comando > file` scrive lo stdout nel file (lo sovrascrive); `>>` lo aggiunge in fondo
- `comando 2> file` scrive lo stderr nel file
- `comando > file 2>&1` scrive tutti e due nello stesso file (`2>&1`: lo stderr va dove va lo stdout)
- `comando 2>/dev/null` butta via gli errori: `/dev/null` è un file che scarta tutto
- `comando < file` usa il file come stdin

## Pipe: lo stdout di un comando nello stdin del successivo

`comando1 | comando2` passa lo stdout del primo come stdin al secondo. Lo stderr non passa: resta a schermo.
Alcuni comandi fatti per stare in una pipe:

- `wc -l` conta le righe
- `sort` ordina, `uniq -c` conta le righe uguali consecutive (dopo un `sort`)
- `head`, `tail`, `grep`: le stesse della lezione 2, ma sullo stdin

Esempio: `ps aux | grep python | wc -l` conta i processi che contengono `python`.

## xargs e find -exec: un comando su ogni risultato

Una pipe passa del **testo**. Ma molti comandi, come `rm` e `chmod`, non leggono lo stdin: vogliono i
nomi dei file come argomenti. `xargs` fa da ponte: legge l'elenco dallo stdin e lo passa come argomenti.

- `find . -name '*.bak' | xargs rm` cancella tutti i `.bak`
- `xargs` divide l'elenco agli spazi: con nomi che contengono spazi usa `find … -print0 | xargs -0 …`
- in alternativa `find . -name '*.bak' -exec rm {} +` fa tutto da solo: `{}` sono i file trovati

Prima di cancellare, lancia sempre solo `find` e guarda l'elenco.

```prova
ls /srv /non-esiste
ls /srv /non-esiste 2>/dev/null
ls /etc | wc -l
grep -c . /etc/passwd
cut -d: -f7 /etc/passwd | sort | uniq -c
```
