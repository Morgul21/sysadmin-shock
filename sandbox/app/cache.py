"""Scalda la cache dell'app: occupa CACHE_MB di memoria e la tocca davvero.

Prima controlla quanta memoria resta nel cgroup del container, come fanno molti runtime:
meglio un errore chiaro all'avvio che farsi uccidere dall'OOM killer a metà.
"""

import sys
from pathlib import Path

CGROUP = Path("/sys/fs/cgroup")
MARGIN_MB = 16


def free_mb():
    try:
        limit = (CGROUP / "memory.max").read_text().strip()
        stat = dict(line.split() for line in (CGROUP / "memory.stat").read_text().splitlines())
    except OSError:
        return None
    if limit == "max":
        return None
    # La page cache si recupera da sola: conta solo la memoria che non si può liberare.
    used = int(stat["anon"]) + int(stat["shmem"])
    return (int(limit) - used) // 2**20


mb = int(sys.argv[1])
free = free_mb()
if free is not None and free < mb + MARGIN_MB:
    sys.exit(f"cache: memoria insufficiente (richiesti {mb} MB)")
cache = b"\x01" * (mb * 2**20)
print(f"cache pronta: {len(cache) // 2**20} MB")
