Le tre terne (proprietario, gruppo, altri) non bastano sempre: a volte serve dare un permesso a **un
solo** utente in più, senza cambiare proprietario e senza aprire il file al gruppo o a tutti. Le
**ACL** (*Access Control List*) servono a questo: sono voci in più, una per utente o per gruppo.

## Come si riconoscono

`ls -l` mostra le tre terne come sempre, più un `+` alla fine dei permessi:

```
-rw-rw-r--+ 1 root app 1200 nov  5 10:00 registro.log
```

Il `+` vuol dire: c'è un'ACL, e le terne non dicono tutto. Da qui in poi `ls -l` non basta più.

## getfacl: leggere l'ACL

```
# file: registro.log
# owner: root
# group: app
user::rw-
user:luca:---
group::rw-
mask::rw-
other::r--
```

- `user::`, `group::`, `other::` (senza nome) sono le tre terne di sempre
- `user:luca:---` è una voce dell'ACL: per l'utente `luca` valgono questi permessi
- `mask::` è il massimo che possono dare le voci con nome e il gruppo: se una voce chiede di più,
  `getfacl` scrive accanto `#effective:` con quello che vale davvero

## Chi vince

Linux controlla in quest'ordine, e si ferma al primo che corrisponde:

1. il proprietario: la terna `user::`
2. una voce `user:nome:` con il tuo nome
3. il gruppo del file e le voci `group:nome:` dei tuoi gruppi
4. gli altri: `other::`

Quindi una voce `user:luca:---` vince sul gruppo, anche se `luca` è nel gruppo e il gruppo può scrivere.
`ls -l` non lo mostra: si vede solo con `getfacl`.

## setfacl: cambiare l'ACL

- `setfacl -m u:anna:r file` aggiunge (o cambia) la voce di `anna`: solo lettura
- `setfacl -m g:tecnici:rw file` lo stesso per un gruppo
- `setfacl -x u:anna file` toglie la voce di `anna`, e solo quella
- `setfacl -b file` toglie **tutta** l'ACL: le altre voci spariscono con lei

```prova
getfacl /var/log/app/app.log
ls -l /srv/esercizi
getfacl /srv/esercizi
```
