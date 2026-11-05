# L'app (UI, CLI, agente, server MCP, eval) in un container. Le sandbox non nascono sul Docker
# del PC ma su un Docker privato (servizio `docker` in compose.yaml): l'app non riceve il socket
# dell'host. Si avvia con `docker compose up --build`.
FROM python:3.12-slim-bookworm

# Solo la CLI di Docker: sandbox.py e lab.py lanciano `docker build/run/exec`.
COPY --from=docker:27.5.1-cli /usr/local/bin/docker /usr/local/bin/docker

WORKDIR /app
COPY . .
# Editable: scenari, lezioni, sandbox/ e .breakfix/ si trovano a partire dal codice (parents[2]).
RUN pip install --no-cache-dir -e . \
    # I test non chiedono né Docker né API key: se falliscono, l'immagine non si builda.
    && python -m unittest discover -s tests \
    && chmod +x docker/entrypoint.sh

ENV BREAKFIX_UI_HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8
EXPOSE 8000
ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["breakfix-ui", "--no-browser"]
