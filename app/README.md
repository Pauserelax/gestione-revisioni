# Gestione Revisioni

Sistema di automazione dello scadenzario revisioni: importa le estrazioni di
WinDrakkar, calcola le scadenze di legge (prima revisione a 4 anni
dall'immatricolazione, poi ogni 2 anni, entro fine mese) e produce le liste di
clienti da contattare.

## Requisiti

Python 3.10+ con `openpyxl` e `xlrd` (`pip install openpyxl xlrd`).

## Dashboard (interfaccia grafica)

```bash
python3 -m revisioni web
```

Si apre nel browser su `http://127.0.0.1:8765` (locale, nessun dato esce dal
computer).

## Flusso operativo

1. **SMS a +2 mesi** — primo contatto: la lista dei veicoli in scadenza tra
   2 mesi si scarica in CSV (bottone in dashboard o `python3 -m revisioni sms`)
   e si carica su **smscafè**. Testo personalizzabile in `dati/sms_testo.txt`
   (segnaposto: {NOME} {MARCA} {MODELLO} {TARGA} {MESE}). Dopo l'invio,
   "Segna tutti come inviati" evita riestrazioni. Chi non ha un cellulare
   valido resta in lista per la chiamata.
2. **Chiamata a +1 mese** — la scheda "Da chiamare" parte da qui: bottoni
   esito Contattato / Appuntamento / Revisione fatta (riprogramma a +2 anni) /
   Non risponde / Auto venduta.
3. **Arretrato** — campagna SMS generica indipendente dalla vettura
   (`python3 -m revisioni sms --arretrato` o bottone dedicato); Cristina
   aggiorna poi i dati del veicolo alle risposte.
4. **Da recuperare** — clienti senza veicolo in scadenzario, con registrazione
   della nuova auto. **Cerca cliente** — storico per nome/telefono/targa/telaio.

## Qualità dei dati

```bash
python3 -m revisioni telefoni            # report: cellulari/fissi/fittizi/mancanti/condivisi
python3 -m revisioni telefoni --excel    # lista Excel di bonifica per l'operatore
python3 -m revisioni flotte              # clienti con molti veicoli (candidati flotta)
python3 -m revisioni flotte --applica    # marca le società evidenti e chi ha 8+ veicoli
python3 -m revisioni flotte "NOME" [--rimuovi]   # gestione manuale singolo cliente
```

- I numeri **fittizi** (cifre ripetute, sequenze 123456, code di 9/0), **non
  validi** e **condivisi** tra decine di clienti sono esclusi dalle liste SMS
  e segnalati in dashboard con un badge rosso.
- I clienti **flotta** (noleggi, società con parco auto, la concessionaria
  stessa) sono esclusi da SMS e liste chiamate; restano nel database e si
  riattivano con `--rimuovi`.

## Uso

Dalla cartella `app/`:

```bash
# 1. Importa un riepilogo mensile C.C.F. esportato da WinDrakkar
python3 -m revisioni importa "../S828555_A_axsccf_luglio 2022.xlsx"

# 2. Vedi i veicoli da contattare (scaduti, in scadenza nel mese, entro 60 gg)
python3 -m revisioni scadenze

# 3. Genera la lista chiamate in Excel (cartella ../liste/)
python3 -m revisioni excel

# 4. Registra l'esito di un contatto (per telaio o targa)
python3 -m revisioni esito GK572PA appuntamento --note "porta anche tagliando"

# Esiti che riprogrammano le ricorrenze:
#   revisione_fatta  → registra la revisione, prossima chiamata a +2 anni
#   non_possiede_piu → dismette il veicolo (esce dalle liste, storico conservato)
python3 -m revisioni esito GK572PA revisione_fatta --data 2026-07-10
python3 -m revisioni esito GK572PA non_possiede_piu --note "auto cambiata"

# Storico completo di un cliente (veicoli, revisioni, contatti)
python3 -m revisioni cliente gianellini

# Il cliente resta nostro anche quando cambia auto:
python3 -m revisioni da-recuperare        # clienti senza veicolo in scadenzario
python3 -m revisioni nuovo-veicolo "BONI STEFANO" --targa GX412KL \
    --marca DC --modello DUSTER --imm 2026-03-15   # basta la targa, telaio facoltativo

# Storico clienti navigabile nel browser (ricerca per nome/telefono/targa/telaio)
python3 -m revisioni storico              # genera liste/storico_clienti.html

# Riepilogo database
python3 -m revisioni stato

# Punti vendita / venditori: elenco ed esclusione dalle liste
python3 -m revisioni puntivendita
python3 -m revisioni escludi livio      # per codice ("48") o nome ("livio")
python3 -m revisioni includi 48         # per reincluderlo
```

I veicoli dei punti vendita esclusi restano nel database ma non compaiono in
scadenzario e liste (si possono rivedere con `--includi-esclusi`).

### Lead Tcar

```bash
# Importa un export lead di Tcar: matching per telaio + arricchimento dati
python3 -m revisioni importa-tcar "../EstrazioneLeads1784211470.xlsx"

# Lead agganciati a veicoli nostri (--tutti per vedere anche gli altri)
python3 -m revisioni lead
```

Il matching usa il **telaio** come chiave esatta. Per i veicoli agganciati il
database viene arricchito con **targa**, **data di immatricolazione reale**
(fonte `tcar`, prioritaria su quella presunta dal report C.C.F.) ed **email**
del cliente. Nella lista chiamate Excel la colonna "Lead Tcar" segnala la
campagna del lead attivo sul veicolo.

Il database SQLite è in `../dati/revisioni.db`.

## Regole applicate

- **Scadenza revisione**: fine mese di (prima immatricolazione + 4 anni); se
  esiste una revisione registrata in `revisioni_effettuate`, fine mese di
  (ultima revisione + 2 anni).
- **Data di riferimento**: la "Data Garanzia" del report C.C.F. quando presente;
  altrimenti il mese del report ricavato dal nome file (es. "luglio 2022"),
  marcato come **presunta** nelle liste.
- **Stati**: `SCADUTA` / `IN_SCADENZA` (nel mese corrente) / `PROSSIMA` (entro
  l'orizzonte `--giorni`, predefinito 60) / `FUTURA`.
- I veicoli con esito `appuntamento` o `non_interessato` per la scadenza
  corrente escono automaticamente dalla lista di chiamata.

## Struttura dati (SQLite)

- `clienti` — anagrafica (nome, telefono, email)
- `veicoli` — parco veicoli, chiave = telaio; targa prevista ma non ancora
  alimentata (il report C.C.F. non la contiene)
- `revisioni_effettuate` — storico revisioni (da alimentare con i dati officina)
- `contatti` — esiti delle chiamate per scadenza
- `import_log` — tracciatura degli import

## Roadmap

1. ✅ Import report C.C.F. WinDrakkar + motore scadenze + lista chiamate Excel
2. ⬜ Import storico clienti officina (serve un'estrazione con targa,
   immatricolazione e date revisioni/tagliandi effettuati)
3. ⬜ Cross-selling: scadenze tagliandi per modello/percorrenza accanto alla revisione
4. ⬜ Email automatiche giornaliere/settimanali/mensili con le liste
5. ⬜ Dashboard grafica con stati di lavorazione
6. ⬜ Aggancio scraper Tcar: matching lead ↔ database per targa/telaio/nome/telefono
7. ⬜ Pacchetto eseguibile per Windows e Mac
