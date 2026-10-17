# Break & Fix Lab

Una palestra per imparare il troubleshooting Linux **da soli**: uno scenario rompe apposta
una sandbox Docker isolata (permessi e memoria), **tu** entri con una shell e la ripari,
uno script di check dice **pass/fail**. Gli agenti non riparano al posto tuo:

- il **tutor** ti dà indizi graduali, con riferimenti alle man page, ma senza mai darti il comando di fix;
- il **fixer** risolve ogni scenario per conto suo: dimostra che si può risolvere ed è il
  riferimento con cui confrontarti (passi, costo). È anche la base dell'eval di traiettoria.

## Architettura

**Scelta: multi-agent con `DagPipeline` per generare gli scenari, single-agent per tutor e fixer.**
Motivazione: generare, applicare e validare uno scenario sono passi con input/output distinti e
verificabili separatamente (un DAG). Tutor e fixer invece sono loop osserva→ragiona→rispondi
che un solo agente con un tool gestisce bene, e si misurano con eval deterministici.

```text
  (roadmap) DagPipeline scenari
  man page ─► Author ─► Breaker ─► Validator ─► scenario (rottura + check + fix di riferimento)
                                                    │
                                                    ▼
  tu ── breakfix-sandbox shell ──────────────► sandbox Docker (no rete, 256MB, 128 pid)
                                                    ▲
  Tutor agent (roadmap) ─┐                          │
  Fixer agent (oggi)  ───┼── MCPClient ──► server MCP: exec_in_sandbox
  Claude Desktop      ───┘
```

Il Validator scarta uno scenario se dopo la rottura il check non fallisce, se dopo il fix di
riferimento il check non passa, oppure se il container non è più sano.

| Pezzo | File |
|---|---|
| Server MCP (FastMCP, 1 tool) | [src/breakfix/server.py](src/breakfix/server.py) |
| Backend sandbox Docker / mock + CLI | [src/breakfix/sandbox.py](src/breakfix/sandbox.py) |
| Immagine della sandbox | [sandbox/Dockerfile](sandbox/Dockerfile) |
| Agente fixer di riferimento (multi-provider, memory persistente) | [src/breakfix/agent.py](src/breakfix/agent.py) |
| Test contratto MCP + integrazione datapizza | [tests/test_server.py](tests/test_server.py) |

## Installazione

Serve Python **3.11–3.13** (datapizza-ai non supporta 3.14). Con `uv` si ottiene senza toccare il Python di sistema:

```powershell
py -m pip install --user uv
py -m uv venv --python 3.12 .venv
py -m uv pip install --python .venv\Scripts\python.exe -e .
.venv\Scripts\Activate.ps1
copy .env.example .env   # poi inserisci la API key
```

## Avvio

```powershell
# 1. Test (non servono né Docker né API key)
python -m unittest discover -s tests -v

# 2. Verifica il collegamento agente -> MCP senza chiamare il modello
$env:BREAKFIX_SANDBOX = "mock"; breakfix-agent --list-tools

# 3. Sandbox vera (Docker Desktop avviato; la prima volta builda l'immagine)
Remove-Item Env:BREAKFIX_SANDBOX
breakfix-sandbox up
breakfix-sandbox exec "chmod 644 /srv/app/run.sh"   # rottura manuale, finché non ci sono gli scenari

# 4a. Ripari tu: shell di root nella sandbox (exit per uscire)
breakfix-sandbox shell

# 4b. ...oppure guardi come lo risolve il fixer di riferimento
breakfix-agent "L'utente app non riesce ad avviare /srv/app/run.sh. Trova la causa e riparala."

breakfix-sandbox down
```

La memory dell'agente è in `.breakfix/memory.json` (`breakfix-agent --reset-memory` per azzerarla).

### Configurazione

| Variabile | Default | Note |
|---|---|---|
| `LLM_PROVIDER` | `openai` | `openai`, `anthropic`, `google`, ... (via `ClientFactory`; extra `pip install -e .[anthropic]`) |
| `LLM_MODEL` | `gpt-5.6-luna` per openai | obbligatoria per gli altri provider |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` | – | oppure `LLM_API_KEY` |
| `LLM_TEMPERATURE` | non inviata | da impostare solo per modelli che la supportano |
| `BREAKFIX_SANDBOX` | `docker` | `mock` per test/demo senza Docker |

## Sicurezza (stato attuale)

- Il tool `exec_in_sandbox` è una shell: **l'isolamento è il container** (`--network none`, 256MB, 128 pid, `no-new-privileges`).
- Output troncato a 4000 caratteri e timeout di 15 s per comando.
- Il server MCP riceve solo l'ambiente minimo più le variabili `BREAKFIX_*`: la API key del modello non gli arriva.
- Guardrail sui comandi e audit trail con ContextTracing: milestone S13.

## Roadmap

- [x] **S12** Architettura + server MCP con un tool collegato all'agente
- [x] Ruoli invertiti: chi impara ripara (`breakfix-sandbox shell`), il fixer diventa il riferimento
- [ ] **S13** Guardrail su `exec_in_sandbox` (denylist, niente `chmod 777`) + ContextTracing; prompt injection di prova piantata in un file della sandbox
- [ ] **S14** 5–8 scenari (permessi + memoria) con rottura, check e fix di riferimento = eval set pass/fail; timeout già presente
- [ ] **S14–S15** Tutor: indizi graduali con citazioni delle man page + guardrail di output "niente spoiler" (blocca le risposte che contengono il fix di riferimento)
- [ ] **S15** Dockerfile dell'app + README finale
- [ ] Extra: DagPipeline Author→Breaker→Validator dalle man page, tutor usato da Claude Desktop, eval in CI

## Note e difficoltà

- `datapizza.tools.MCPClient` importa `streamablehttp_client`, rinominato in MCP SDK 2.x: il progetto fissa `mcp<2` e usa FastMCP v1.
- `ClientFactory` invia `temperature=0.7` di default e `gpt-5.6-luna` risponde 400: la temperatura va passata esplicitamente (`None` = non inviata).
