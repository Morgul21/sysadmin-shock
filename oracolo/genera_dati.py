"""Genera i file dell'Oracolo (oracolo/dati/): sempre gli stessi, con un seme fisso.

I dati li scriviamo noi, non il modello: così le risposte giuste sono note (evals/oracolo.toml) e il
comando proposto dall'Oracolo si può verificare eseguendolo. Si rilancia solo per cambiare i dati:
    python oracolo/genera_dati.py
e poi si aggiornano le risposte attese dell'eval (`breakfix-oracolo verifica` dice quali non tornano).
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent / "dati"
rng = random.Random(20261116)

COGNOMI = ["Rossi", "Russo", "Ferrari", "Esposito", "Bianchi", "Romano", "Colombo", "Ricci", "Marino", "Greco",
           "Bruno", "Gallo", "Conti", "De Luca", "Mancini", "Costa", "Giordano", "Rizzo", "Lombardi", "Moretti",
           "Barbieri", "Fontana", "Santoro", "Mariani", "Rinaldi", "Caruso", "Ferrara", "Galli", "Martini", "Leone"]
NOMI = ["Marco", "Giulia", "Luca", "Anna", "Paolo", "Sara", "Andrea", "Chiara", "Matteo", "Elena", "Davide",
        "Francesca", "Simone", "Laura", "Stefano", "Martina", "Giorgio", "Valentina", "Alessandro", "Federica"]
REPARTI = ["amministrazione", "magazzino", "vendite", "IT", "produzione", "logistica"]
CITTA = ["Torino", "Milano", "Bologna", "Roma", "Napoli", "Bari", "Firenze", "Genova"]


def dipendenti() -> str:
    righe = ["cognome,nome,reparto,anno_assunzione,citta"]
    usati = set()
    while len(righe) < 41:
        persona = (rng.choice(COGNOMI), rng.choice(NOMI))
        if persona in usati:
            continue
        usati.add(persona)
        righe.append(f"{persona[0]},{persona[1]},{rng.choice(REPARTI)},{rng.randint(2003, 2025)},{rng.choice(CITTA)}")
    return "\n".join(righe) + "\n"


APP_EVENTI = [
    ("INFO", "http", "GET /ordini 200 in {ms} ms"),
    ("INFO", "http", "POST /ordini 201 in {ms} ms"),
    ("INFO", "cache", "cache aggiornata: {n} voci"),
    ("INFO", "backup", "backup completato in {s} s"),
    ("WARN", "cache", "cache quasi piena: {p}%"),
    ("WARN", "http", "risposta lenta: GET /report {ms} ms"),
    ("WARN", "db", "query lenta sulla tabella ordini: {ms} ms"),
    ("ERROR", "db", "connessione al database rifiutata"),
    ("ERROR", "db", "timeout della query dopo 30 s"),
    ("ERROR", "http", "POST /ordini 500: errore interno"),
    ("ERROR", "backup", "backup fallito: spazio su disco esaurito"),
]
APP_PESI = [30, 20, 10, 4, 6, 6, 5, 4, 3, 3, 2]


def app_log() -> str:
    t = datetime(2026, 11, 12, 7, 58, 0)
    righe = []
    for _ in range(220):
        t += timedelta(seconds=rng.randint(5, 240))
        livello, componente, testo = rng.choices(APP_EVENTI, weights=APP_PESI)[0]
        testo = testo.format(ms=rng.randint(12, 4800), n=rng.randint(100, 9000), s=rng.randint(30, 600),
                             p=rng.randint(85, 99))
        righe.append(f"{t:%Y-%m-%d %H:%M:%S} {livello:<5} [{componente}] {testo}")
    return "\n".join(righe) + "\n"


def kern_log() -> str:
    """Come `dmesg`: secondi dall'avvio tra parentesi quadre, poi il messaggio. Tra gli eventi, un disco
    (sdb) che comincia a dare errori di I/O e il file system che lo rimonta in sola lettura."""
    t = 0.0
    righe = []
    avvio = [
        "Linux version 6.1.0-26-amd64 (debian-kernel@lists.debian.org)",
        "Command line: BOOT_IMAGE=/boot/vmlinuz-6.1.0-26-amd64 root=/dev/sda1 ro quiet",
        "Memory: 16302412K/16700416K available",
        "ata1: SATA link up 6.0 Gbps (SStatus 133 SControl 300)",
        "ata2: SATA link up 3.0 Gbps (SStatus 123 SControl 300)",
        "sd 0:0:0:0: [sda] 976773168 512-byte logical blocks: (500 GB/466 GiB)",
        "sd 1:0:0:0: [sdb] 3907029168 512-byte logical blocks: (2.00 TB/1.82 TiB)",
        "EXT4-fs (sda1): mounted filesystem with ordered data mode",
        "EXT4-fs (sdb1): mounted filesystem with ordered data mode",
        "e1000e 0000:00:1f.6 eth0: NIC Link is Up 1000 Mbps Full Duplex",
    ]
    for messaggio in avvio:
        t += rng.uniform(0.05, 1.5)
        righe.append(f"[{t:12.6f}] {messaggio}")
    eventi = [
        "usb 1-2: new high-speed USB device number 3 using xhci_hcd",
        "usb 1-2: USB disconnect, device number 3",
        "e1000e 0000:00:1f.6 eth0: NIC Link is Down",
        "e1000e 0000:00:1f.6 eth0: NIC Link is Up 1000 Mbps Full Duplex",
        "TCP: request_sock_TCP: Possible SYN flooding on port 443. Sending cookies.",
        "gestionale[{pid}]: segfault at 0 ip 000055d4c1a2b3c4 sp 00007ffd2e1c8a90 error 4",
    ]
    for _ in range(60):
        t += rng.uniform(20, 900)
        righe.append(f"[{t:12.6f}] " + rng.choice(eventi).format(pid=rng.randint(1000, 30000)))
    for _ in range(14):  # il disco sdb che si guasta
        t += rng.uniform(5, 120)
        settore = rng.randint(100_000_000, 3_900_000_000)
        righe.append(f"[{t:12.6f}] blk_update_request: I/O error, dev sdb, sector {settore} op 0x0:(READ)")
        if rng.random() < 0.5:
            righe.append(f"[{t + 0.001:12.6f}] Buffer I/O error on dev sdb1, logical block {settore // 8}, async page read")
    t += 3
    righe.append(f"[{t:12.6f}] EXT4-fs error (device sdb1): ext4_find_entry:1658: inode #2: comm ls: reading directory lblock 0")
    righe.append(f"[{t + 0.2:12.6f}] EXT4-fs (sdb1): Remounting filesystem read-only")
    for _ in range(3):  # l'OOM killer, con le tre righe che scrive un kernel 6.1 vero
        t += rng.uniform(300, 2000)
        pid = rng.randint(1000, 30000)
        righe.append(f"[{t:12.6f}] python3 invoked oom-killer: gfp_mask=0x140cca(GFP_HIGHUSER_MOVABLE|__GFP_COMP), "
                     "order=0, oom_score_adj=0")
        righe.append(f"[{t + 0.004:12.6f}] oom-kill:constraint=CONSTRAINT_NONE,nodemask=(null),cpuset=/,mems_allowed=0,"
                     f"global_oom,task_memcg=/system.slice/gestionale.service,task=python3,pid={pid},uid=1000")
        righe.append(f"[{t + 0.005:12.6f}] Out of memory: Killed process {pid} (python3) total-vm:4123456kB, "
                     "anon-rss:3890120kB, file-rss:0kB, shmem-rss:0kB, UID:1000 pgtables:7712kB oom_score_adj:0")
    return "\n".join(righe) + "\n"


def archivio() -> str:
    """L'elenco dei file dell'archivio: percorso, dimensione in KB, data di modifica. Lo script di
    preparazione li crea davvero (head -c e touch -d): servono per du, find -size, find -newermt, sort."""
    righe = ["# percorso dimensione_kb data_modifica"]
    cartelle = {"backup": (2000, 8000), "export": (50, 900), "log-vecchi": (10, 400), "tmp": (1, 60)}
    inizio = datetime(2026, 6, 1)
    for cartella, (minimo, massimo) in cartelle.items():
        for i in range(1, rng.randint(5, 9)):
            data = inizio + timedelta(days=rng.randint(0, 160), hours=rng.randint(0, 23))
            estensione = {"backup": "tar.gz", "export": "csv", "log-vecchi": "log.gz", "tmp": "tmp"}[cartella]
            righe.append(f"archivio/{cartella}/{cartella}-{data:%Y%m%d}-{i}.{estensione} "
                         f"{rng.randint(minimo, massimo)} {data:%Y-%m-%d}")
    return "\n".join(righe) + "\n"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for name, text in (("dipendenti.csv", dipendenti()), ("app.log", app_log()), ("kern.log", kern_log()),
                       ("archivio.txt", archivio())):
        (OUT / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"{name}: {text.count(chr(10))} righe")


if __name__ == "__main__":
    main()
