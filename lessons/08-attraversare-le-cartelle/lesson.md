Un file con i permessi giusti può essere comunque irraggiungibile: per arrivarci bisogna passare
da tutte le cartelle del suo percorso, e anche le cartelle hanno dei permessi.

## r, w, x su una cartella

Una cartella è un elenco di nomi. Le stesse lettere dei file vogliono dire:

- `r`: **elencare** i nomi che contiene (`ls`)
- `w`: **creare, rinominare e cancellare** file al suo interno (anche file non tuoi!)
- `x`: **attraversarla**: entrarci con `cd` e raggiungere i file al suo interno, se ne conosci il nome

Le combinazioni contano:

- `r-x`: il caso normale, si entra e si elenca
- `--x`: si entra e si apre un file di cui si conosce il nome, ma `ls` dà `Permission denied`
- `r--`: `ls` mostra i nomi (con errori), ma non si entra e non si apre niente

Per questo le cartelle di solito sono `755` o `750`, e i file `644` o `640`: la `x` su una cartella non
è "esecuzione", è il permesso di passarci.

## ls -ld: i permessi della cartella, non del contenuto

`ls -l cartella` mostra quello che c'è dentro. Per vedere la cartella stessa serve `-d`:
`ls -ld cartella`.

## Il percorso intero: namei -l

Per aprire `/srv/app/run.sh` servono la `x` su `/`, su `/srv` e su `/srv/app`, e poi i permessi sul
file. Basta che manchi in una cartella, e il file è irraggiungibile: l'errore è sempre lo stesso,
`Permission denied`, e sembra un problema del file.

`namei -l percorso` mostra una riga per ogni pezzo del percorso, dalla radice al file: permessi,
proprietario, gruppo. È il modo più rapido per trovare il pezzo che blocca.

Come sempre, da `root` non si vede il problema: va provato come l'utente giusto, con `runuser -u app -- …`.

```prova
ls -ld /srv /srv/app
namei -l /srv/app/run.sh
namei -l /var/log/app/app.log
runuser -u app -- ls /root
```
