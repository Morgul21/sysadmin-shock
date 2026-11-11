# Sysadmin Shock: come si incastrano i pezzi

Questa guida è pensata per chi sta iniziando con agenti, tool e MCP. Parte da ciò che è
implementato nel progetto, senza richiedere conoscenze pregresse. Per installazione,
configurazione completa e dettagli tecnici, vedi il [README](README.md).

> **In breve:** questa applicazione crea un piccolo ambiente Linux in un container, applica
> un guasto previsto da uno scenario e lascia a te il compito di diagnosticarlo e ripararlo.
> Un tutor AI ti aiuta senza voler svelare la soluzione; uno script verifica il risultato.
> Un altro agente, il fixer, può risolvere lo stesso problema come riferimento.

## 1. Prima di tutto: che cosa succede oggi?

Ci sono tre precisazioni importanti:

1. **Non è un agente a inventare o applicare il guasto.** Gli scenari sono preparati in
   anticipo: il programma ricrea una sandbox sana ed esegue lo script `break.sh` dello
   scenario selezionato. Generare scenari con più agenti è un'idea futura, non una
   funzionalità attuale.
2. **Il tutor conosce la soluzione, ma è istruito a non rivelarla.** Il codice controlla
   anche le sue risposte; tuttavia questa protezione non garantisce che ogni possibile
   spoiler venga intercettato.
3. **Il giudice LLM non decide se hai riparato il ticket.** Il pulsante di verifica esegue
   uno script `check.sh`. Il giudice LLM serve invece negli *eval*, cioè nei test del tutor:
   valuta la qualità delle risposte del tutor, non il tuo intervento sulla sandbox.

### Il percorso di chi studia

```text
Browser: Basi oppure Challenge
             |
             v
Il programma crea una sandbox Docker nuova
             |
             +-- Basi: uno script prepara l'esercizio
             |
             +-- Challenge: break.sh applica un guasto previsto
                                    |
                                    v
                         Leggi il ticket e usi il terminale
                                    |
                         +----------+----------+
                         |                     |
                         v                     v
                   Chiedi indizi        Chiedi al tutor AI
                                               |
                                     Controllo anti-spoiler
                         |                     |
                         +----------+----------+
                                    |
                                    v
                       Provi a risolvere tu il problema
                                    |
                                    v
                       "Verifica" esegue check.sh
                                    |
                                    v
                                PASS / FAIL
```

Il fixer e gli eval sono percorsi separati: non vengono chiamati automaticamente per ogni
ticket risolto dall'utente.

## 2. Il vocabolario essenziale

| Termine | Significato semplice | Nel progetto |
|---|---|---|
| **LLM o modello** | Il componente che genera testo e, se supportato, propone chiamate a tool. Non è automaticamente un programma autonomo. | Per esempio Qwen tramite Ollama; il provider è configurabile. |
| **Prompt** | Le istruzioni e le informazioni inviate al modello. Il *system prompt* descrive il ruolo e le regole; la domanda e il contesto completano l'input. | Il tutor riceve regole, ticket, indizi, soluzione di riferimento e domanda. |
| **Agente** | Un programma che usa un modello per svolgere un compito, con un ruolo e un contesto; può anche disporre di tool e decidere quali chiamare. | Il fixer usa un tool; il tutor è realizzato come agente senza tool. |
| **Tool** | Una funzione che un programma o un agente può invocare per ottenere dati o produrre un effetto nel mondo esterno. Il modello ne richiede l'uso; è il codice a eseguirla. | `exec_in_sandbox` esegue un comando Linux nel container e restituisce il risultato. |
| **Server MCP** | Un programma che espone capacità, ad esempio tool, tramite il protocollo MCP (*Model Context Protocol*). | Il server `breakfix-sandbox` espone `exec_in_sandbox`. |
| **Client MCP** | Il componente che si collega al server, scopre i tool e permette di invocarli. | Il fixer usa `MCPClient` della libreria datapizza. |
| **Guardrail** | Un controllo posto attorno al modello o a un tool per limitare comportamenti indesiderati. Non equivale necessariamente a una garanzia assoluta. | Uno controlla i comandi del fixer; un altro cerca spoiler nella risposta del tutor. |
| **Eval** | Una prova ripetibile che misura se un sistema si comporta come desiderato. | Si misura sia la capacità del fixer di riparare, sia la qualità del tutor. |
| **Giudice LLM** | Un modello a cui si chiede di valutare un'altra risposta seguendo una rubrica. Può sbagliare e va confrontato con giudizi umani. | Nell'eval del tutor valuta soluzione, gradualità e correttezza. |
| **Sandbox** | Un ambiente separato in cui sperimentare, con limiti e precauzioni. | Un container Debian ricreato per esercizi e ticket. |

Un modello, quindi, **non è la stessa cosa di un agente**: lo stesso modello può essere
usato con istruzioni diverse per fare il tutor, il fixer o il giudice. Può anche essere
usato direttamente da codice, come avviene per il giudice dell'eval.

## 3. Immagine, container, esercizi e challenge

Un'**immagine Docker** è il modello da cui creare un ambiente; un **container** è
un'istanza in esecuzione di quell'immagine. Il [Dockerfile della sandbox](sandbox/Dockerfile)
prepara una Debian minimale con un piccolo servizio simulato, `gestionale`, i suoi file e
strumenti Linux utili agli esercizi.

Quando scegli una challenge, il programma:

1. crea un container nuovo a partire dall'immagine sana;
2. esegue `break.sh`, che altera l'ambiente secondo lo scenario scelto;
3. prova ad avviare il servizio, così l'errore viene registrato nel log;
4. ti presenta il ticket e una shell nella sandbox;
5. su richiesta, esegue `check.sh` e mostra l'esito.

Il codice che gestisce gli scenari è in [lab.py](src/breakfix/lab.py); quello che crea e
usa il container è in [sandbox.py](src/breakfix/sandbox.py).

Ogni cartella in [scenarios](scenarios/) contiene:

| File | Ruolo |
|---|---|
| `scenario.toml` | Metadati, ticket, indizi, man page, lezioni collegate e regole anti-spoiler. |
| `break.sh` | Applica il guasto previsto. Non è generato da un modello durante l'esercizio. |
| `check.sh` | Controlla se lo stato finale soddisfa i requisiti. |
| `fix.sh` | Soluzione di riferimento usata per validare lo scenario e come contesto del tutor. Non viene eseguita per risolvere il ticket al posto tuo. |

**Il check guarda il risultato, non pretende che tu abbia digitato esattamente il comando
di riferimento.** Può accettare una soluzione alternativa se rispetta le condizioni
previste. Il comando `breakfix-sandbox validate` controlla tra l'altro che lo scenario
sano passi, quello rotto fallisca e quello riparato con il fix di riferimento passi.

Le **Basi** seguono un meccanismo simile, in [lessons](lessons/): ogni lezione ha una
spiegazione e degli esercizi con `setup.sh`, `check.sh` e `solution.sh`. Alcuni chiedono di
cambiare lo stato del sistema, altri di scrivere una risposta. I dati possono variare a
ogni avvio, così bisogna osservare l'ambiente invece di ricordare una risposta.

## 4. L'interfaccia: chi fa cosa?

La pagina nel browser è la parte visibile, ma non contiene tutta la logica:

```text
Browser
  |  richieste HTTP: lezioni, ticket, tutor, verifica
  v
Applicazione web FastAPI  ----->  codice del laboratorio e script degli scenari
  |
  |  WebSocket: dati del terminale
  v
Docker API  ----->  bash nel container sandbox
```

La pagina usa xterm.js per mostrare un **terminale vero**, collegato via WebSocket a una
shell Bash nel container. I comandi che scrivi nel terminale vengono eseguiti direttamente
nella sandbox: **non passano dal tool MCP né dal suo guardrail**. Il guardrail del tool
protegge il percorso dell'agente, non quello della shell interattiva.

Il backend è in [web.py](src/breakfix/web.py); i file della pagina sono in
[static](src/breakfix/static/). Il progresso visualizzato è salvato nel browser; il
contesto della conversazione con il tutor è invece salvato dall'applicazione.

## 5. Il fixer: un agente con un tool

Il **fixer** è l'agente che prova a diagnosticare e riparare autonomamente. Serve come
riferimento e per gli esperimenti: non è il tutor e non è necessario per usare le challenge.
Il suo codice è in [agent.py](src/breakfix/agent.py).

```text
Ticket
  |
  v
Fixer (ruolo + modello + memoria + tool disponibili)
  |
  |  1. il modello decide di chiamare exec_in_sandbox("...")
  v
MCPClient -- stdio --> server MCP
                          |
                          |  2. controlla il comando con il guardrail
                          v
                    DockerSandbox --> container Linux
                          |
                          |  3. exit code, stdout, stderr, eventuale troncamento
                          v
                     ritorno al fixer
                          |
                          v
            il modello osserva e decide il prossimo passo
```

Per esempio, il fixer può chiedere un comando di lettura come `ls -l /srv/app`, riceverne
l'output, formulare un'ipotesi e poi richiedere un altro comando. Questo ciclo continua
entro un limite di passi; alla fine l'agente produce una risposta. **Dire «ho risolto» non
prova che sia vero**: nell'eval del fixer il verdetto viene dal `check.sh` dello scenario.

Il server in [server.py](src/breakfix/server.py) espone un solo tool,
`exec_in_sandbox`. Il client avvia il server come sottoprocesso e comunica tramite
**stdio**, cioè i suoi flussi standard: in questa configurazione non serve immaginare un
server web pubblico. MCP è il protocollo per presentare e chiamare la capacità; il codice
del tool, il controllo dei comandi e Docker fanno il lavoro concreto. Non tutti i tool
devono usare MCP: una funzione può anche essere collegata direttamente a un agente.

Il guardrail in [guardrail.py](src/breakfix/guardrail.py) blocca alcune classi di comandi
pericolosi prima che arrivino al container. È una lista di regole, non una prova che
qualsiasi comando non bloccato sia sicuro. Il fixer conserva inoltre una memoria tra
esecuzioni; la CLI permette di azzerarla con `breakfix-agent --reset-memory`.

## 6. Il tutor: un agente senza tool

Il tutor, implementato in [tutor.py](src/breakfix/tutor.py), ha un obiettivo diverso:
**aiutarti a ragionare senza riparare al posto tuo**. Non ha `exec_in_sandbox` né altri
tool: il programma raccoglie il contesto e glielo passa prima di chiedere la risposta.

```text
Domanda + ticket + indizi già disponibili
        + ultimi comandi dalla history
        + mappa dell'ambiente + fix di riferimento
                            |
                            v
                 Tutor / modello configurato
                            |
                            v
             Risposta grezza del modello
                            |
                  Controllo anti-spoiler
                    /                \
        nessuna regola scatta     regola scatta
                 |                    |
        risposta del modello    indizio scritto a mano
                    \                /
                     risposta mostrata
```

Il tutor vede gli ultimi comandi registrati nella history, **non una lettura completa e
automatica di tutto lo stato del container**. Riceve anche quanti indizi hai aperto, per
adattare il livello della risposta. La conversazione è condivisa fra UI e CLI e riparte
quando si crea una nuova sandbox.

La configurazione d'esempio in [.env.example](.env.example) usa Ollama con
`breakfix-qwen3-8b`, basato su Qwen; sono configurabili anche altri provider e modelli.
Ollama è il servizio che rende disponibile il modello: non è né l'agente né il server MCP.
La scelta del modello e delle sue istruzioni riguarda il tutor, non lo script di verifica.

### «Non riesce a darmi la soluzione» è una garanzia?

È l'**obiettivo**, non una garanzia matematica. La difesa ha due livelli:

1. Il prompt vieta al modello di dare la correzione, anche se qualcuno cerca di convincerlo
   a ignorare le istruzioni.
2. Il codice confronta la risposta con le espressioni regolari `spoilers` dello scenario.
   Se trova una corrispondenza, sostituisce la risposta con un indizio scritto a mano.

Il controllo riconosce forme di comando previste dalle regole, ma può non riconoscere una
soluzione espressa in altri modi, per esempio una parafrasi. Anche un indizio troppo
rivelatore potrebbe sfuggirgli. Il giudice LLM serve a **misurare** anche questi problemi
negli eval: non interviene normalmente tra il tutor e l'utente.

## 7. Due valutazioni diverse: verifica del sistema e giudice del tutor

| Domanda | Chi risponde | Quando | Come |
|---|---|---|---|
| «La challenge è stata riparata?» | `check.sh` | Quando chiedi la verifica; anche nell'eval del fixer. | Controlli programmati sullo stato e sul servizio: PASS o FAIL. |
| «La risposta del tutor è buona?» | Giudice LLM, più controllo anti-spoiler | Durante `breakfix-tutor-eval`. | Il modello giudice valuta la risposta grezza secondo una rubrica; il codice verifica anche la risposta mostrata. |

La rubrica in [tutor_eval.py](src/breakfix/tutor_eval.py) chiede al giudice tre valutazioni
indipendenti: `niente_soluzione`, `graduale` e `corretta`. L'eval prova domande normali e
tentativi di convincere il tutor a rivelare la soluzione (*jailbreak*). Se il guardrail
sostituisce una risposta, l'eval distingue la prestazione del modello da quella del
sistema completo.

Il giudice non è infallibile: la **calibrazione** confronta i suoi giudizi con esempi
etichettati da persone in [judge-calibration.toml](evals/judge-calibration.toml). Il
provider e il modello del giudice si possono configurare separatamente; se non specificati,
si usa quello del tutor. Anche una buona calibrazione su questi esempi non dimostra che il
giudice sarà sempre corretto.

## 8. Tool o multiagente: quando scegliere cosa?

Non sono due alternative equivalenti:

- Un **tool** dà a un programma o a un agente una capacità: leggere un dato, eseguire un
  comando, interrogare un database, chiamare un'API. È adatto quando serve un'operazione
  concreta con input e output definiti. Se il flusso è interamente prevedibile, spesso
  basta codice normale, senza alcun agente.
- Un **agente** usa un modello per decidere come procedere in un compito non completamente
  prevedibile. Può usare uno o più tool, ma non è obbligatorio: il tutor di questo progetto
  non ne usa.
- Un sistema **multiagente** coordina più agenti che si passano risultati o collaborano a
  un obiettivo comune. Serve un meccanismo di orchestrazione: chi parte, che cosa riceve,
  come si controllano gli output e come si gestiscono errori o disaccordi.

Una regola pratica:

1. **Hai solo bisogno di eseguire un'operazione nota?** Parti da una funzione o da uno
   script: ad esempio `check.sh`.
2. **Serve scegliere dinamicamente quali operazioni fare in base ai risultati?** Valuta
   un singolo agente con i tool necessari: ad esempio il fixer.
3. **Esistono fasi o competenze davvero distinte, con risultati intermedi verificabili,
   o lavoro indipendente parallelizzabile?** Valuta più agenti, se i benefici giustificano
   più chiamate al modello, latenza, costi e complessità.

Il progetto contiene **più ruoli AI**, ma questo non significa che il percorso del ticket
sia un sistema multiagente: fixer e tutor non collaborano tra loro. Il giudice è una
chiamata separata nell'eval del tutor. Il [README](README.md#architettura) propone come
possibile evoluzione una pipeline di agenti per creare e validare nuovi scenari; oggi la
validazione degli scenari esistenti è svolta dal codice e dagli script.

## 9. Sicurezza e tracce: cosa protegge cosa

- La sandbox gira senza rete, con limiti di memoria e processi e `no-new-privileges`; i
  comandi del tool hanno anche timeout e output limitato. Sono misure di contenimento,
  **non isolamento perfetto**.
- Con [compose.yaml](compose.yaml), l'app usa un Docker privato (*Docker-in-Docker*)
  invece del socket Docker del PC. Il servizio Docker privato è comunque `privileged`:
  anche questa scelta non elimina tutti i rischi.
- La UI apre una shell root nella sandbox e per impostazione prevista è raggiungibile
  solo dal PC locale. Non esporla a una rete non fidata.
- Il guardrail dei comandi è una denylist aggirabile; quello del tutor riconosce solo
  gli spoiler coperti dalle sue regole. I prompt non sono confini di sicurezza affidabili.
- L'output dei comandi, i log, il ticket e le domande possono contenere istruzioni
  ingannevoli (*prompt injection*). Il progetto tratta tali contenuti come dati e include
  un esempio nel log della sandbox.
- Le esecuzioni di fixer e tutor producono audit in `.breakfix/audit/`; gli eval producono
  report in `.breakfix/eval/`. L'audit del tutor può contenere **anche la risposta grezza
  bloccata**, quindi può contenere spoiler. Memoria e audit possono conservare contenuti
  dei comandi: vanno trattati con attenzione, soprattutto se si usa un provider remoto.
- Il check gira nel container, dove chi studia è root: è utile per gli esercizi, ma non è
  una verifica a prova di un partecipante intenzionato a manipolare l'ambiente.

## 10. Da dove iniziare concretamente

Per seguire il percorso dal browser, consulta prima i prerequisiti e i comandi di
[installazione e avvio](README.md#installazione). In alternativa all'installazione Python
locale, con Docker Desktop puoi avviare l'app con `docker compose up --build -d` dalla
cartella del progetto e aprire `http://localhost:8000`. Per il tutor serve inoltre un
modello configurato e raggiungibile; con Ollama locale vedi le istruzioni del README.

Una volta aperta la pagina:

1. Parti da **Basi**, leggi una spiegazione e prova un esercizio.
2. Passa a una **Challenge**, leggi il ticket e osserva l'ambiente dal terminale.
3. Se ti blocchi, apri un indizio o fai una domanda al tutor.
4. Prova la tua correzione e premi **Verifica**.
5. Solo dopo, se vuoi esplorare il funzionamento interno, osserva gli scenari e prova
   separatamente l'eval del fixer o quello del tutor.

Per orientarti nel codice, un ordine utile è:
[lab.py](src/breakfix/lab.py) → [sandbox.py](src/breakfix/sandbox.py) →
[web.py](src/breakfix/web.py) → [tutor.py](src/breakfix/tutor.py) →
[agent.py](src/breakfix/agent.py) → [server.py](src/breakfix/server.py) →
[tutor_eval.py](src/breakfix/tutor_eval.py).
