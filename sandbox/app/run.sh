#!/bin/sh
# Avvio dell'app: legge la configurazione, registra l'avvio, scalda la cache in memoria.
set -eu
. /srv/app/app.conf
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) INFO  app: avvio del servizio" >> /var/log/app/app.log
date -u +%s > "$DATA_DIR/last-start"
python3 /srv/app/cache.py "$CACHE_MB"
echo "app avviata"
