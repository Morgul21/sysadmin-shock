# Immagine della sandbox: l'ambiente che gli scenari rompono e che il fixer ripara.
# Il container gira senza rete, quindi tutto quello che serve va installato qui.
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends procps acl less \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash app \
    && mkdir -p /srv/app \
    && printf '#!/bin/sh\necho "app avviata"\n' > /srv/app/run.sh \
    && chmod 755 /srv/app/run.sh \
    && chown -R app:app /srv/app

# Log applicativo con una prompt injection piantata: chi diagnostica lo legge per primo.
# Serve a dimostrare che anche se il modello obbedisce, il guardrail del server blocca.
COPY app.log /var/log/app/app.log

CMD ["sleep", "infinity"]
