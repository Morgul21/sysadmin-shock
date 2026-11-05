#!/bin/sh
# Prima di avviare l'app: il Docker privato deve rispondere e avere l'immagine della sandbox.
set -e

i=0
until docker info >/dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -ge 60 ]; then
        echo "Il Docker privato non risponde ($DOCKER_HOST)" >&2
        exit 1
    fi
    sleep 1
done

# Builda l'immagine della sandbox (dalla seconda volta usa la cache) e crea un container sano.
breakfix-sandbox up

exec "$@"
