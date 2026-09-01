# Gestione Revisioni

Sistema per automatizzare lo scadenzario delle revisioni auto di una
concessionaria/officina: importa le estrazioni del gestionale, calcola le
scadenze di legge (prima revisione a 4 anni dall'immatricolazione, poi ogni
2 anni) e produce le liste di clienti da contattare, con dashboard operativa,
campagne SMS/email e gestione della qualità dei dati.

Gira in locale, senza installazioni: un server Python con libreria standard
serve una dashboard che si apre nel browser. Nessun dato esce dal computer.

## Avvio rapido (con dati di prova)

```bash
cd app
pip install openpyxl xlrd pypdf

# carica dati fittizi per vedere l'app in funzione (nessun dato reale)
python3 -m revisioni reset --conferma --demo

# avvia la dashboard (si apre nel browser)
python3 -m revisioni web
```

## Uso quotidiano

A fine giornata conviene chiudere la finestra della dashboard e riaprirla il
giorno dopo. La classificazione delle scadenze (SMS a +2 mesi, chiamata a +1
mese, mese corrente, arretrato) dipende dalla data del giorno: se la finestra
resta aperta a lungo — tipicamente a cavallo del primo del mese — la dashboard
si riallinea comunque da sola alla prima richiesta del giorno nuovo, ma un
riavvio pulito è la prassi consigliata. Se si rilancia l'avvio mentre la
dashboard è già in esecuzione, non ne parte una seconda: viene solo riaperto il
browser su quella attiva.

## Funzionalità

- **Scadenzario** per fasi operative: SMS a +2 mesi, chiamata a +1 mese,
  scadenze del mese corrente, arretrato.
- **Dashboard web**: liste di chiamata con esiti (contattato, appuntamento,
  revisione fatta → riprogramma a +2 anni, auto venduta → recupero cliente),
  ricerca cliente con storico, correzione telefoni inline.
- **Import multi-formato**: report C.C.F. del gestionale, registro
  immatricolazioni, export lead, export PDF del portale revisioni (Dekra).
  I duplicati sono neutralizzati per telaio/targa; ogni import arricchisce i
  dati senza mai degradarli e riporta in gestione i veicoli archiviati che
  ritrovano una data valida.
- **Storico revisioni reali**: i passaggi in linea documentati dal portale
  alimentano lo scadenzario con date certe e distinguono i veicoli del parco
  clienti da quelli esterni (candidati al cross-selling).
- **Statistiche**: scheda con i numeri della linea revisioni — quota parco
  vs esterni, clienti fidelizzati, revisioni mese per mese e potenziale di
  ritorno nei 12 mesi successivi.
- **Liste di riattivazione**: Cold (scaduti mai contattati), Riscalda clienti
  (scaduti da ricontattare: possibile nuovo veicolo), Dati mancanti (veicoli
  senza data: una telefonata li fa entrare in scadenzario).
- **Qualità dei dati**: validatore telefoni (fittizi, non validi, condivisi),
  rilevamento flotte, fusione clienti/veicoli duplicati — sempre con decisione
  dell'operatore, mai automatica.
- **Campagne**: liste SMS (≤160 caratteri, personalizzate col nome) ed email,
  con code d'invio tracciate.
- **Distribuzione**: pacchetto portabile Windows con Python incorporato,
  backup automatico del database, uso da cartella condivisa una postazione
  alla volta.

## Struttura

```
app/revisioni/       codice del programma
  cli.py             comandi da terminale
  web.py             dashboard web
  db.py              database SQLite e logica dati
  scadenze.py        motore di calcolo delle scadenze
  parser_*.py        importatori dei vari formati
  telefoni.py        validazione numeri
  sms.py             composizione messaggi ed export
  modelli.py         codici modello -> nomi commerciali
  demo.py            generatore di dati fittizi
crea_pacchetto_windows.sh   build del pacchetto portabile
```

I dati reali (database, file Excel dei clienti) non sono nel repository: sono
esclusi da `.gitignore` per tutelare la privacy dei clienti. Il comando
`reset --demo` genera dati di prova completamente fittizi.

## Comandi principali

```bash
python3 -m revisioni web                       # dashboard
python3 -m revisioni importa-immatricolazioni <file/cartella>
python3 -m revisioni importa-dekra <pdf/cartella>   # export portale revisioni
python3 -m revisioni scadenze [--mese AAAA-MM]
python3 -m revisioni sms [--arretrato]         # export campagna SMS
python3 -m revisioni telefoni [--excel]        # report qualità telefoni
python3 -m revisioni reset [--conferma] [--demo]
python3 -m revisioni backup
```

## Licenza

Copyright (C) 2026 Jean-François Rosé Yapi

Questo programma è software libero: puoi ridistribuirlo e/o modificarlo secondo
i termini della **GNU Affero General Public License versione 3 (AGPL-3.0)**
come pubblicata dalla Free Software Foundation. Vedi il file [LICENSE](LICENSE).

In pratica: sei libero di usarlo, studiarlo e modificarlo, ma ogni versione
modificata — anche se offerta come servizio online — deve restare open source
sotto la stessa licenza e mantenere questa attribuzione. I dati dei clienti non
fanno parte del progetto e restano privati.

Il programma è distribuito nella speranza che sia utile, ma SENZA ALCUNA
GARANZIA, nei limiti consentiti dalla legge applicabile.
