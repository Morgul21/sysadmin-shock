Quando un'applicazione viene fermata perché "finisce la memoria", o un disco si riempie, bisogna
misurare: quanta memoria c'è davvero, chi la usa, dove sono finiti i file.

## free: la memoria del sistema

`free -m` mostra la memoria in megabyte (`-h` sceglie l'unità da solo):

- `total`: tutta la RAM
- `used`: quella usata dai processi
- `buff/cache`: quella usata come cache dei file, che il kernel libera quando serve
- `available`: quella che un programma nuovo può ancora ottenere. È il numero che conta, non `free`

## Il limite di un container: i cgroup

In un container `free` mente: legge la memoria della **macchina** che lo ospita, non quella che il
container può usare. Il limite vero lo applica il kernel con i **cgroup**, e si legge in
`/sys/fs/cgroup/`:

- `memory.max`: il limite, in byte (`max` se non c'è limite)
- `memory.current`: quanta ne sta usando adesso tutto il container
- `memory.stat`: il dettaglio, per esempio `anon` (memoria dei processi) e `shmem` (file in memoria)

Quando `memory.current` arriva a `memory.max`, il kernel ferma un processo (l'*OOM killer*), anche se
`free` dice che c'è memoria libera.

## df: quanto sono pieni i filesystem

`df -h` mostra ogni filesystem montato: dimensione, usato, disponibile, `Use%`, e dove è montato.
`df -h cartella` mostra solo quello che contiene la cartella.

Alcuni filesystem stanno in memoria: `tmpfs`, come `/dev/shm`. I file scritti lì occupano RAM e contano
nel limite del container. Un file dimenticato in `/dev/shm` è memoria occupata che nessun processo
possiede: `ps` non la mostra.

## du: cosa occupa spazio

`df` dice quanto è pieno, `du` dice cosa lo riempie:

- `du -sh cartella`: il totale di una cartella
- `du -sh cartella/*`: il totale di ogni elemento, per trovare il più grande
- `du -sh cartella/* | sort -h`: lo stesso, in ordine di dimensione

```prova
free -m
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
grep -E '^(anon|shmem) ' /sys/fs/cgroup/memory.stat
df -h
du -sh /srv/app /var/log
```
