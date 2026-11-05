Nella lezione 5 i permessi si leggevano; qui si cambiano, con `chmod`. Lo stesso permesso
si può scrivere in due modi: in **ottale** o in **simbolico**.

## Ottale: una cifra per terna

Ogni lettera vale un numero, e una terna è la somma delle sue lettere:

```
r = 4   w = 2   x = 1

rwx = 4+2+1 = 7      r-x = 4+1 = 5
rw- = 4+2   = 6      r-- = 4   = 4
---         = 0
```

Tre terne, tre cifre: proprietario, gruppo, altri. `rwxr-x---` è `750`.
`stat -c %a file` mostra i permessi di un file in ottale.

I valori che si incontrano più spesso:

- `755` (`rwxr-xr-x`): programmi, script e cartelle
- `644` (`rw-r--r--`): file normali
- `640` (`rw-r-----`): file con segreti che il gruppo deve leggere, come una configurazione con una password
- `600` (`rw-------`): solo il proprietario, per chiavi e credenziali

`chmod 640 file` **riscrive tutte e tre le terne**: quello che c'era prima non conta.

## Simbolico: cambi solo quello che nomini

La forma è *chi*, *operazione*, *permessi*:

- chi: `u` proprietario, `g` gruppo, `o` altri, `a` tutti e tre
- operazione: `+` aggiunge, `-` toglie, `=` imposta esattamente
- permessi: `r`, `w`, `x`

`chmod g+w file` aggiunge la scrittura al gruppo e lascia il resto com'è; `chmod o= file` toglie
tutto agli altri. Più modifiche si separano con la virgola: `chmod u+x,g-w file`.

Quale usare: l'ottale quando sai lo stato finale che vuoi; il simbolico quando devi cambiare un
permesso senza toccare gli altri, soprattutto su tanti file con permessi diversi tra loro.
`chmod -R` applica la modifica a una cartella e a tutto quello che contiene.

## Perché non 777

`777` è `rwxrwxrwx`: chiunque sul server può **modificare** il file. Su uno script di avvio vuol
dire che qualunque utente può riscriverlo, e l'app eseguirà quello che ci ha messo. Il
`Permission denied` sparisce, ma al suo posto c'è una falla. Il fix giusto aggiunge solo il
permesso che manca, e solo a chi serve.

```prova
stat -c '%a %A %n' /srv/app/*
ls -l /srv/esercizi
```
