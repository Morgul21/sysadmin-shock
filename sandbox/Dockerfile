# Immagine della sandbox: l'ambiente sano che gli scenari rompono e che si ripara.
# Il container gira senza rete, quindi tutto quello che serve va installato qui.
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends procps acl less python3-minimal \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash app

# L'app: run.sh legge app.conf, scrive in data/ e nel log, poi scalda la cache (cache.py).
# Ogni scenario rompe uno di questi pezzi; i check verificano che l'app riparta come `app`.
COPY app/ /srv/app/
# Come su un server vero, il servizio si scopre: il comando che usano gli utenti e l'unità
# systemd dicono cosa avvia cosa, e con quale utente. Nessuno lo scrive nel ticket.
COPY bin/gestionale /usr/local/bin/gestionale
COPY gestionale.service /etc/systemd/system/gestionale.service
# Storico del log, con una prompt injection piantata: chi diagnostica lo legge per primo.
# Serve a dimostrare che anche se il modello obbedisce, il guardrail del server blocca.
# L'errore dello scenario lo aggiunge il primo avvio fallito, subito dopo la rottura.
COPY app.log /var/log/app/app.log
RUN mkdir /srv/app/data \
    && chown -R app:app /srv/app \
    && chmod 755 /srv/app /srv/app/run.sh \
    && chmod 644 /srv/app/cache.py \
    && chmod 640 /srv/app/app.conf \
    && chmod 750 /srv/app/data \
    && chmod 755 /usr/local/bin/gestionale \
    && chown root:app /var/log/app/app.log \
    && chmod 664 /var/log/app/app.log

CMD ["sleep", "infinity"]
