"""Database SQLite del parco clienti/veicoli e dello stato dei contatti."""

from __future__ import annotations

import calendar
import sqlite3
from datetime import date, datetime
from pathlib import Path

from .parser_ccf import RigaVeicolo

SCHEMA = """
CREATE TABLE IF NOT EXISTS clienti (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    telefono TEXT,
    email TEXT,
    UNIQUE (nome, telefono)
);

-- Punti vendita / venditori: escluso = 1 li toglie da scadenzario e liste.
CREATE TABLE IF NOT EXISTS punti_vendita (
    codice TEXT PRIMARY KEY,
    descrizione TEXT,
    escluso INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS veicoli (
    id INTEGER PRIMARY KEY,
    telaio TEXT UNIQUE,                 -- può mancare per inserimenti manuali (basta la targa)
    targa TEXT,
    marca TEXT,
    modello TEXT,
    versione TEXT,
    serie TEXT,
    punto_vendita TEXT,
    cliente_id INTEGER NOT NULL REFERENCES clienti(id),
    data_immatricolazione TEXT,      -- ISO; per ora data garanzia o fine mese report
    fonte_data TEXT,                 -- data_garanzia | mese_report | manuale | sconosciuta
    data_ordine TEXT,
    documento_acquisto TEXT,
    listino TEXT,
    file_origine TEXT,
    attivo INTEGER NOT NULL DEFAULT 1   -- 0 = il cliente non possiede più il veicolo
);

-- Storico revisioni effettuate (alimentato in futuro dai dati officina).
CREATE TABLE IF NOT EXISTS revisioni_effettuate (
    id INTEGER PRIMARY KEY,
    veicolo_id INTEGER NOT NULL REFERENCES veicoli(id),
    data_revisione TEXT NOT NULL,
    fonte TEXT
);

-- Passaggi in linea revisione dal portale Dekra: prova che la revisione è
-- stata fatta DA NOI. veicolo_id agganciato quando telaio/targa è nel parco.
CREATE TABLE IF NOT EXISTS revisioni_dekra (
    id INTEGER PRIMARY KEY,
    targa TEXT NOT NULL,
    telaio TEXT,
    categoria TEXT,                  -- M1 | N1 | M1G | N1G
    tipo_operazione TEXT,            -- REV = revisione; altri codici = altre pratiche
    esito TEXT,                      -- REGOLARE | SOSPESO (1) | RIPETERE (2) | vuoto
    data_prenotazione TEXT,
    data_revisione TEXT NOT NULL,
    codice_pratica TEXT,
    veicolo_id INTEGER REFERENCES veicoli(id),
    file_origine TEXT,
    importato_at TEXT,
    UNIQUE (targa, data_revisione, tipo_operazione)
);
CREATE INDEX IF NOT EXISTS idx_dekra_veicolo ON revisioni_dekra(veicolo_id);
CREATE INDEX IF NOT EXISTS idx_dekra_targa ON revisioni_dekra(targa);

-- Esiti dei contatti per lo scadenzario (dashboard/liste chiamata).
CREATE TABLE IF NOT EXISTS contatti (
    id INTEGER PRIMARY KEY,
    veicolo_id INTEGER NOT NULL REFERENCES veicoli(id),
    scadenza TEXT NOT NULL,          -- la scadenza revisione a cui si riferisce il contatto
    data_contatto TEXT NOT NULL,
    esito TEXT NOT NULL,             -- contattato | appuntamento | non_interessato | irraggiungibile
    note TEXT
);

-- Lead importati dagli export Tcar; veicolo_id valorizzato quando il telaio
-- corrisponde a un veicolo del nostro parco.
CREATE TABLE IF NOT EXISTS lead_tcar (
    id INTEGER PRIMARY KEY,
    tcar_id INTEGER UNIQUE,
    codice_cm TEXT,
    marca TEXT,
    tipologia TEXT,
    campagna TEXT,
    creazione TEXT,
    scadenza_lead TEXT,
    stato TEXT,
    assegnatario TEXT,
    cognome TEXT,
    nome TEXT,
    email TEXT,
    telefoni TEXT,
    targa TEXT,
    telaio TEXT,
    modello TEXT,
    data_immatricolazione TEXT,
    veicolo_id INTEGER REFERENCES veicoli(id),
    file_origine TEXT,
    importato_at TEXT
);

CREATE TABLE IF NOT EXISTS import_log (
    id INTEGER PRIMARY KEY,
    file TEXT NOT NULL,
    data_import TEXT NOT NULL,
    righe_lette INTEGER,
    veicoli_nuovi INTEGER,
    veicoli_aggiornati INTEGER
);

-- Nomi per cui l'operatore ha deciso che gli omonimi sono persone diverse.
CREATE TABLE IF NOT EXISTS omonimi_ignorati (
    nome TEXT PRIMARY KEY,
    deciso_il TEXT
);

-- Coppie di veicoli che l'operatore ha dichiarato NON essere doppioni.
CREATE TABLE IF NOT EXISTS doppioni_ignorati (
    chiave TEXT PRIMARY KEY,     -- "idminore-idmaggiore"
    deciso_il TEXT
);

-- Gruppi di varianti-nome che l'operatore ha dichiarato essere soggetti diversi.
CREATE TABLE IF NOT EXISTS varianti_ignorate (
    chiave TEXT PRIMARY KEY,     -- nucleo del nome
    deciso_il TEXT
);

-- Code di invio bulk: selezioni dell'operatore per SMS (smscafè) o email (Brevo).
CREATE TABLE IF NOT EXISTS code_invio (
    id INTEGER PRIMARY KEY,
    veicolo_id INTEGER NOT NULL REFERENCES veicoli(id),
    canale TEXT NOT NULL,            -- sms | brevo
    scadenza TEXT,                   -- scadenza revisione a cui si riferisce
    aggiunto_il TEXT NOT NULL,
    inviato_il TEXT                  -- NULL = in coda; data = invio effettuato
);
CREATE INDEX IF NOT EXISTS idx_code_invio ON code_invio(canale, inviato_il, veicolo_id);

CREATE INDEX IF NOT EXISTS idx_veicoli_cliente ON veicoli(cliente_id, attivo);
CREATE INDEX IF NOT EXISTS idx_veicoli_targa ON veicoli(targa);
CREATE INDEX IF NOT EXISTS idx_clienti_nome ON clienti(nome);
CREATE INDEX IF NOT EXISTS idx_contatti_veicolo ON contatti(veicolo_id, data_contatto);
CREATE INDEX IF NOT EXISTS idx_revisioni_veicolo ON revisioni_effettuate(veicolo_id, data_revisione);
CREATE INDEX IF NOT EXISTS idx_lead_veicolo ON lead_tcar(veicolo_id);
"""


def apri_db(percorso: Path, condivisa_tra_thread: bool = False) -> sqlite3.Connection:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(percorso, check_same_thread=not condivisa_tra_thread)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migra(conn)
    return conn


def _migra(conn: sqlite3.Connection) -> None:
    """Adegua database creati con versioni precedenti dello schema."""
    colonne = {r["name"] for r in conn.execute("PRAGMA table_info(veicoli)")}
    if "attivo" not in colonne:
        conn.execute("ALTER TABLE veicoli ADD COLUMN attivo INTEGER NOT NULL DEFAULT 1")
        conn.commit()
    colonne_clienti = {r["name"] for r in conn.execute("PRAGMA table_info(clienti)")}
    if "flotta" not in colonne_clienti:
        # 1 = flotta/azienda con parco veicoli: esclusa da liste SMS e chiamate.
        conn.execute("ALTER TABLE clienti ADD COLUMN flotta INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    colonne = {r["name"] for r in conn.execute("PRAGMA table_info(veicoli)")}
    if "archiviato" not in colonne:
        # 1 = fuori gestione (es. pre-2022 senza dati validabili): escluso da
        # scadenzario, liste e "da recuperare"; resta nello storico cliente.
        conn.execute("ALTER TABLE veicoli ADD COLUMN archiviato INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    # telaio era NOT NULL: ricostruzione tabella per ammettere veicoli con sola targa.
    if any(r["name"] == "telaio" and r["notnull"] for r in conn.execute("PRAGMA table_info(veicoli)")):
        campi = ("id, telaio, targa, marca, modello, versione, serie, punto_vendita, cliente_id, "
                 "data_immatricolazione, fonte_data, data_ordine, documento_acquisto, listino, "
                 "file_origine, attivo")
        conn.executescript(f"""
            ALTER TABLE veicoli RENAME TO veicoli_vecchia;
            CREATE TABLE veicoli (
                id INTEGER PRIMARY KEY,
                telaio TEXT UNIQUE,
                targa TEXT,
                marca TEXT,
                modello TEXT,
                versione TEXT,
                serie TEXT,
                punto_vendita TEXT,
                cliente_id INTEGER NOT NULL REFERENCES clienti(id),
                data_immatricolazione TEXT,
                fonte_data TEXT,
                data_ordine TEXT,
                documento_acquisto TEXT,
                listino TEXT,
                file_origine TEXT,
                attivo INTEGER NOT NULL DEFAULT 1
            );
            INSERT INTO veicoli ({campi}) SELECT {campi} FROM veicoli_vecchia;
            DROP TABLE veicoli_vecchia;
        """)
        conn.commit()


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def importa_righe(conn: sqlite3.Connection, righe: list[RigaVeicolo], file_origine: str,
                  punti_vendita: dict[str, str] | None = None) -> dict:
    """Inserisce/aggiorna clienti e veicoli. Il telaio è la chiave dei veicoli."""
    for codice, descrizione in (punti_vendita or {}).items():
        conn.execute(
            """INSERT INTO punti_vendita (codice, descrizione) VALUES (?, ?)
               ON CONFLICT(codice) DO UPDATE SET descrizione = excluded.descrizione
               WHERE excluded.descrizione != ''""",
            (codice, descrizione),
        )
    nuovi = aggiornati = 0
    for r in righe:
        cliente_id = _trova_o_crea_cliente(conn, r.ragione_sociale, r.telefono or None, None)

        esistente = conn.execute(
            "SELECT id, fonte_data FROM veicoli WHERE telaio = ?", (r.telaio,)
        ).fetchone()
        if esistente:
            conn.execute(
                """UPDATE veicoli SET marca=?, modello=?, versione=?, serie=?, punto_vendita=?,
                   cliente_id=?, data_ordine=?, documento_acquisto=?, listino=?, file_origine=?
                   WHERE id=?""",
                (r.marca, r.modello, r.versione, r.serie, r.punto_vendita,
                 cliente_id, _iso(r.data_ordine), r.documento_acquisto, r.listino,
                 file_origine, esistente["id"]),
            )
            # La data di immatricolazione si aggiorna solo se la fonte nuova è
            # più affidabile di quella già registrata (mai degradare).
            if r.data_riferimento and PRIORITA_FONTE.get(r.fonte_data, -1) > PRIORITA_FONTE.get(esistente["fonte_data"] or "sconosciuta", -1):
                conn.execute(
                    "UPDATE veicoli SET data_immatricolazione = ?, fonte_data = ? WHERE id = ?",
                    (_iso(r.data_riferimento), r.fonte_data, esistente["id"]),
                )
            aggiornati += 1
        else:
            conn.execute(
                """INSERT INTO veicoli (telaio, marca, modello, versione, serie, punto_vendita,
                   cliente_id, data_immatricolazione, fonte_data, data_ordine,
                   documento_acquisto, listino, file_origine)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (r.telaio, r.marca, r.modello, r.versione, r.serie, r.punto_vendita,
                 cliente_id, _iso(r.data_riferimento), r.fonte_data, _iso(r.data_ordine),
                 r.documento_acquisto, r.listino, file_origine),
            )
            nuovi += 1

    conn.execute(
        "INSERT INTO import_log (file, data_import, righe_lette, veicoli_nuovi, veicoli_aggiornati) VALUES (?, ?, ?, ?, ?)",
        (file_origine, datetime.now().isoformat(timespec="seconds"), len(righe), nuovi, aggiornati),
    )
    conn.commit()
    return {"righe": len(righe), "nuovi": nuovi, "aggiornati": aggiornati}


# Affidabilità delle fonti della data di immatricolazione: una fonte più
# affidabile non viene mai sovrascritta da una meno affidabile.
# Il registro immatricolazioni del collega è la FONTE UFFICIALE (decisione
# utente 17/07/2026): vince su tutto tranne le correzioni manuali.
PRIORITA_FONTE = {"manuale": 4, "immatricolazioni": 3, "tcar": 2, "storico": 1,
                  "data_garanzia": 1, "mese_report": 0, "stimata": 0, "sconosciuta": -1}

# Corrispondenza tra i nomi marca dei file immatricolazioni e i codici WinDrakkar.
MARCHE_EQUIVALENTI = {"RENAULT": {"RE", "R1", "RENAULT"}, "DACIA": {"DC", "DACIA"}}

# Feedback storici di Cristina che indicano che il cliente non possiede più l'auto.
FEEDBACK_DISMESSA = ("VENDUTA", "AUTO VENDUTA", "DEMOLITA", "RUBATA")


def _trova_o_crea_cliente(conn: sqlite3.Connection, nome: str, telefono: str | None, email: str | None) -> int:
    """Dedup clienti: prima (nome, telefono), poi nome esatto con match unico."""
    if telefono:
        row = conn.execute(
            "SELECT id FROM clienti WHERE nome = ? AND telefono = ?", (nome, telefono)
        ).fetchone()
        if row:
            return row["id"]
    omonimi = conn.execute("SELECT * FROM clienti WHERE nome = ?", (nome,)).fetchall()
    if len(omonimi) == 1:
        c = omonimi[0]
        if telefono and not c["telefono"]:
            conn.execute("UPDATE clienti SET telefono = ? WHERE id = ?", (telefono, c["id"]))
        if email and not c["email"]:
            conn.execute("UPDATE clienti SET email = ? WHERE id = ?", (email, c["id"]))
        return c["id"]
    if len(omonimi) > 1 and telefono:
        for c in omonimi:
            if c["telefono"] == telefono:
                return c["id"]
    if omonimi and not telefono:
        return omonimi[0]["id"]
    return conn.execute(
        "INSERT INTO clienti (nome, telefono, email) VALUES (?, ?, ?)",
        (nome, telefono, email),
    ).lastrowid


def importa_storico(conn: sqlite3.Connection, righe, file_origine: str) -> dict:
    """Importa le righe del parser storico con dedup su telaio/targa/cliente."""
    nuovi = aggiornati = revisioni = feedbacks = dismessi = 0
    adesso = datetime.now().isoformat(timespec="seconds")
    for r in righe:
        cliente_id = _trova_o_crea_cliente(conn, r.cliente, r.telefoni[0] if r.telefoni else None, r.email or None)

        veicolo = None
        if r.telaio:
            veicolo = conn.execute("SELECT * FROM veicoli WHERE telaio = ?", (r.telaio,)).fetchone()
        if veicolo is None and r.targa:
            veicolo = conn.execute(
                "SELECT * FROM veicoli WHERE targa = ? AND (telaio IS NULL OR telaio = '' OR ? = '')",
                (r.targa, r.telaio),
            ).fetchone()

        if veicolo is None:
            veicolo_id = conn.execute(
                """INSERT INTO veicoli (telaio, targa, marca, modello, cliente_id,
                   data_immatricolazione, fonte_data, file_origine)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (r.telaio or None, r.targa or None, r.marca, r.modello, cliente_id,
                 _iso(r.data_immatricolazione), "storico" if r.data_immatricolazione else "sconosciuta",
                 file_origine),
            ).lastrowid
            nuovi += 1
        else:
            veicolo_id = veicolo["id"]
            modifiche = {}
            if r.targa and not veicolo["targa"]:
                modifiche["targa"] = r.targa
            if r.telaio and not veicolo["telaio"]:
                modifiche["telaio"] = r.telaio
            if r.marca and not veicolo["marca"]:
                modifiche["marca"] = r.marca
            if r.modello and not veicolo["modello"]:
                modifiche["modello"] = r.modello
            if r.data_immatricolazione and PRIORITA_FONTE.get("storico", 0) > PRIORITA_FONTE.get(veicolo["fonte_data"] or "sconosciuta", -1):
                modifiche["data_immatricolazione"] = r.data_immatricolazione.isoformat()
                modifiche["fonte_data"] = "storico"
            if modifiche:
                assegnazioni = ", ".join(f"{k} = ?" for k in modifiche)
                conn.execute(f"UPDATE veicoli SET {assegnazioni} WHERE id = ?",
                             (*modifiche.values(), veicolo_id))
            aggiornati += 1

        ultima_rev, fonte_rev = r.ultima_revisione, "storico"
        if not ultima_rev and r.scadenza_dichiarata:
            # La scadenza dichiarata da Cristina implica: ultima revisione = scadenza - 2 anni
            # (fine mese). Così la prossima scadenza calcolata coincide con quella dichiarata.
            s = r.scadenza_dichiarata
            ultima_rev = date(s.year - 2, s.month, calendar.monthrange(s.year - 2, s.month)[1])
            fonte_rev = "storico-scadenza"
        if ultima_rev:
            gia = conn.execute(
                "SELECT 1 FROM revisioni_effettuate WHERE veicolo_id = ? AND data_revisione = ?",
                (veicolo_id, ultima_rev.isoformat()),
            ).fetchone()
            if not gia:
                conn.execute(
                    "INSERT INTO revisioni_effettuate (veicolo_id, data_revisione, fonte) VALUES (?, ?, ?)",
                    (veicolo_id, ultima_rev.isoformat(), fonte_rev),
                )
                revisioni += 1

        if r.feedback:
            nota = f"{r.note} [import {file_origine}/{r.foglio}]".strip()
            gia = conn.execute(
                "SELECT 1 FROM contatti WHERE veicolo_id = ? AND esito = ? AND note = ?",
                (veicolo_id, r.feedback, nota),
            ).fetchone()
            if not gia:
                conn.execute(
                    "INSERT INTO contatti (veicolo_id, scadenza, data_contatto, esito, note) VALUES (?, '', ?, ?, ?)",
                    (veicolo_id, adesso, r.feedback, nota),
                )
                feedbacks += 1
            if r.feedback in FEEDBACK_DISMESSA:
                conn.execute("UPDATE veicoli SET attivo = 0 WHERE id = ?", (veicolo_id,))
                dismessi += 1

    ripristina_con_dati(conn)
    conn.execute(
        "INSERT INTO import_log (file, data_import, righe_lette, veicoli_nuovi, veicoli_aggiornati) VALUES (?, ?, ?, ?, ?)",
        (file_origine, adesso, len(righe), nuovi, aggiornati),
    )
    conn.commit()
    return {"righe": len(righe), "nuovi": nuovi, "aggiornati": aggiornati,
            "revisioni": revisioni, "feedback": feedbacks, "dismessi": dismessi}


def importa_dekra(conn: sqlite3.Connection, righe, file_origine: str) -> dict:
    """Importa i passaggi in linea revisione dal PDF del portale Dekra.

    Ogni riga viene salvata in revisioni_dekra (dedup su targa+data+operazione)
    e agganciata al parco per telaio o targa; gli esiti REGOLARE alimentano
    revisioni_effettuate (fonte 'dekra': date reali, migliorano lo scadenzario).
    """
    adesso = datetime.now().isoformat(timespec="seconds")
    nuove = doppie = match = targhe_aggiunte = telai_aggiunti = 0
    for r in righe:
        if not r.data_revisione:
            continue
        veicolo = None
        if r.telaio:
            veicolo = conn.execute("SELECT * FROM veicoli WHERE telaio = ?", (r.telaio,)).fetchone()
        if veicolo is None and r.targa:
            veicolo = conn.execute(
                "SELECT * FROM veicoli WHERE targa = ? AND (telaio IS NULL OR telaio = '')",
                (r.targa,),
            ).fetchone()
        veicolo_id = veicolo["id"] if veicolo else None
        if veicolo:
            match += 1
            if r.targa and not veicolo["targa"]:
                conn.execute("UPDATE veicoli SET targa = ? WHERE id = ?", (r.targa, veicolo_id))
                targhe_aggiunte += 1
            if r.telaio and not veicolo["telaio"]:
                conn.execute("UPDATE veicoli SET telaio = ? WHERE id = ?", (r.telaio, veicolo_id))
                telai_aggiunti += 1

        gia = conn.execute(
            "SELECT id, veicolo_id FROM revisioni_dekra WHERE targa = ? AND data_revisione = ? AND tipo_operazione = ?",
            (r.targa, r.data_revisione.isoformat(), r.tipo_operazione),
        ).fetchone()
        if gia:
            doppie += 1
            if veicolo_id and not gia["veicolo_id"]:
                conn.execute("UPDATE revisioni_dekra SET veicolo_id = ? WHERE id = ?",
                             (veicolo_id, gia["id"]))
        else:
            conn.execute(
                """INSERT INTO revisioni_dekra (targa, telaio, categoria, tipo_operazione, esito,
                   data_prenotazione, data_revisione, codice_pratica, veicolo_id, file_origine, importato_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (r.targa, r.telaio or None, r.categoria, r.tipo_operazione, r.esito,
                 _iso(r.data_prenotazione), r.data_revisione.isoformat(), r.codice_pratica,
                 veicolo_id, file_origine, adesso),
            )
            nuove += 1

    revisioni = riagganciate = 0
    riagganciate = riaggancia_dekra(conn)
    # Sincronizza le revisioni REGOLARI agganciate in revisioni_effettuate (idempotente).
    revisioni = conn.execute(
        """INSERT INTO revisioni_effettuate (veicolo_id, data_revisione, fonte)
           SELECT d.veicolo_id, d.data_revisione, 'dekra' FROM revisioni_dekra d
           WHERE d.veicolo_id IS NOT NULL AND d.tipo_operazione = 'REV'
             AND d.esito LIKE 'REGOLARE%'
             AND NOT EXISTS (SELECT 1 FROM revisioni_effettuate r
                             WHERE r.veicolo_id = d.veicolo_id
                               AND r.data_revisione = d.data_revisione)""",
    ).rowcount

    ripristinati = ripristina_con_dati(conn)

    conn.execute(
        "INSERT INTO import_log (file, data_import, righe_lette, veicoli_nuovi, veicoli_aggiornati) VALUES (?, ?, ?, 0, ?)",
        (file_origine, adesso, len(righe), match),
    )
    conn.commit()
    non_agganciate = conn.execute(
        "SELECT COUNT(*) AS n FROM revisioni_dekra WHERE veicolo_id IS NULL").fetchone()["n"]
    abituali = conn.execute(
        """SELECT COUNT(*) AS n FROM (SELECT targa FROM revisioni_dekra
           WHERE tipo_operazione = 'REV' GROUP BY targa HAVING COUNT(*) >= 2)""").fetchone()["n"]
    return {"righe": len(righe), "nuove": nuove, "doppie": doppie, "match": match,
            "revisioni": revisioni, "riagganciate": riagganciate,
            "targhe_aggiunte": targhe_aggiunte, "telai_aggiunti": telai_aggiunti,
            "non_agganciate": non_agganciate, "abituali": abituali,
            "ripristinati": ripristinati}


def riaggancia_dekra(conn: sqlite3.Connection) -> int:
    """Riprova ad agganciare al parco i passaggi Dekra rimasti orfani
    (il veicolo può comparire con un import successivo)."""
    n = 0
    for d in conn.execute("SELECT * FROM revisioni_dekra WHERE veicolo_id IS NULL").fetchall():
        veicolo = None
        if d["telaio"]:
            veicolo = conn.execute("SELECT id FROM veicoli WHERE telaio = ?", (d["telaio"],)).fetchone()
        if veicolo is None and d["targa"]:
            veicolo = conn.execute(
                "SELECT id FROM veicoli WHERE targa = ? AND (telaio IS NULL OR telaio = '')",
                (d["targa"],),
            ).fetchone()
        if veicolo:
            conn.execute("UPDATE revisioni_dekra SET veicolo_id = ? WHERE id = ?",
                         (veicolo["id"], d["id"]))
            n += 1
    return n


def ripristina_con_dati(conn: sqlite3.Connection) -> int:
    """Riporta in gestione i veicoli archiviati per mancanza di dati che nel
    frattempo hanno ottenuto una data validabile (es. revisione reale da Dekra):
    ogni import deve colmare i dati mancanti, non lasciarli fuori gestione."""
    n = conn.execute(
        """UPDATE veicoli SET archiviato = 0
           WHERE attivo = 1 AND IFNULL(archiviato, 0) = 1
             AND EXISTS (SELECT 1 FROM revisioni_effettuate r WHERE r.veicolo_id = veicoli.id)"""
    ).rowcount
    conn.commit()
    return n


def veicoli_dati_mancanti(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Veicoli attivi fuori gestione perché senza data immatricolazione né
    revisione nota: con una telefonata si recupera la data e rientrano in
    scadenzario (pulsante "Revisione fatta")."""
    return conn.execute(
        """SELECT v.id AS veicolo_id, v.targa, v.telaio, v.marca, v.modello,
                  v.file_origine, c.nome AS cliente, c.telefono
           FROM veicoli v JOIN clienti c ON c.id = v.cliente_id
           LEFT JOIN punti_vendita pv ON pv.codice = v.punto_vendita
           WHERE v.attivo = 1 AND IFNULL(v.archiviato, 0) = 1
             AND v.data_immatricolazione IS NULL
             AND NOT EXISTS (SELECT 1 FROM revisioni_effettuate r WHERE r.veicolo_id = v.id)
             AND IFNULL(pv.escluso, 0) = 0 AND IFNULL(c.flotta, 0) = 0
           ORDER BY c.nome"""
    ).fetchall()


def statistiche_dekra(conn: sqlite3.Connection) -> dict:
    """Numeri per la scheda Statistiche della dashboard: attività della linea
    revisioni (portale Dekra), quota parco nostro vs veicoli esterni,
    fidelizzazione e potenziale di ritorno mese per mese (ultima revisione
    REGOLARE + 2 anni)."""
    tot = conn.execute(
        """SELECT COUNT(*) AS passaggi, COUNT(DISTINCT targa) AS targhe,
                  MIN(data_revisione) AS dal, MAX(data_revisione) AS al,
                  SUM(veicolo_id IS NOT NULL) AS passaggi_nostri,
                  SUM(veicolo_id IS NULL) AS passaggi_esterni,
                  COUNT(DISTINCT CASE WHEN veicolo_id IS NOT NULL THEN targa END) AS targhe_nostre,
                  COUNT(DISTINCT CASE WHEN veicolo_id IS NULL THEN targa END) AS targhe_esterne
           FROM revisioni_dekra WHERE tipo_operazione = 'REV'"""
    ).fetchone()
    if not tot["passaggi"]:
        return {"vuoto": True}

    ritorni = {r["passaggi"]: r["targhe"] for r in conn.execute(
        """SELECT passaggi, COUNT(*) AS targhe FROM
           (SELECT COUNT(*) AS passaggi FROM revisioni_dekra
            WHERE tipo_operazione = 'REV' GROUP BY targa)
           GROUP BY passaggi"""
    )}
    fidelizzate = sum(n for p, n in ritorni.items() if p >= 2)

    mensile = [dict(r) for r in conn.execute(
        """SELECT substr(data_revisione, 1, 7) AS mese,
                  SUM(veicolo_id IS NOT NULL) AS nostri,
                  SUM(veicolo_id IS NULL) AS esterni
           FROM revisioni_dekra WHERE tipo_operazione = 'REV'
           GROUP BY mese ORDER BY mese"""
    )]

    # Potenziale di ritorno: per ogni targa con almeno una revisione REGOLARE,
    # la prossima è dovuta nel mese di (ultima revisione + 2 anni).
    oggi = date.today()
    mese_corrente = f"{oggi.year:04d}-{oggi.month:02d}"
    prossimi = []
    a, m = oggi.year, oggi.month
    for _ in range(12):
        prossimi.append(f"{a:04d}-{m:02d}")
        m += 1
        if m > 12:
            a, m = a + 1, 1
    potenziale = {mese: {"mese": mese, "nostri": 0, "esterni": 0} for mese in prossimi}
    arretrato = {"nostri": 0, "esterni": 0}
    for r in conn.execute(
        """SELECT targa, MAX(data_revisione) AS ultima,
                  MAX(veicolo_id) IS NOT NULL AS nostro
           FROM revisioni_dekra
           WHERE tipo_operazione = 'REV' AND esito LIKE 'REGOLARE%'
           GROUP BY targa"""
    ):
        dovuta = f"{int(r['ultima'][:4]) + 2:04d}-{r['ultima'][5:7]}"
        chi = "nostri" if r["nostro"] else "esterni"
        if dovuta < mese_corrente:
            arretrato[chi] += 1
        elif dovuta in potenziale:
            potenziale[dovuta][chi] += 1

    return {
        "passaggi": tot["passaggi"], "targhe": tot["targhe"],
        "dal": tot["dal"], "al": tot["al"],
        "passaggi_nostri": tot["passaggi_nostri"], "passaggi_esterni": tot["passaggi_esterni"],
        "targhe_nostre": tot["targhe_nostre"], "targhe_esterne": tot["targhe_esterne"],
        "fidelizzate": fidelizzate,
        "ritorni": [{"passaggi": p, "targhe": n} for p, n in sorted(ritorni.items())],
        "mensile": mensile,
        "potenziale": list(potenziale.values()),
        "arretrato": arretrato,
    }


def importa_lead_tcar(conn: sqlite3.Connection, leads, file_origine: str) -> dict:
    """Importa i lead Tcar, li aggancia ai veicoli per telaio e arricchisce
    il database (targa, data immatricolazione reale, email)."""
    from .parser_tcar import LeadTcar  # noqa: F401 (documentazione del tipo atteso)

    match = arricchiti = 0
    adesso = datetime.now().isoformat(timespec="seconds")
    for lead in leads:
        veicolo = None
        if lead.telaio:
            veicolo = conn.execute(
                "SELECT v.*, c.email AS cliente_email FROM veicoli v JOIN clienti c ON c.id = v.cliente_id WHERE v.telaio = ?",
                (lead.telaio,),
            ).fetchone()
        if veicolo:
            match += 1
            modifiche = {}
            if lead.targa and not veicolo["targa"]:
                modifiche["targa"] = lead.targa
            if lead.data_immatricolazione and (
                PRIORITA_FONTE.get("tcar", 0) > PRIORITA_FONTE.get(veicolo["fonte_data"] or "sconosciuta", -1)
            ):
                modifiche["data_immatricolazione"] = lead.data_immatricolazione.isoformat()
                modifiche["fonte_data"] = "tcar"
            if modifiche:
                assegnazioni = ", ".join(f"{k} = ?" for k in modifiche)
                conn.execute(
                    f"UPDATE veicoli SET {assegnazioni} WHERE id = ?",
                    (*modifiche.values(), veicolo["id"]),
                )
                arricchiti += 1
            if lead.email and not veicolo["cliente_email"]:
                conn.execute(
                    "UPDATE clienti SET email = ? WHERE id = ?",
                    (lead.email, veicolo["cliente_id"]),
                )

        conn.execute(
            """INSERT INTO lead_tcar (tcar_id, codice_cm, marca, tipologia, campagna, creazione,
               scadenza_lead, stato, assegnatario, cognome, nome, email, telefoni, targa, telaio,
               modello, data_immatricolazione, veicolo_id, file_origine, importato_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(tcar_id) DO UPDATE SET
                 stato = excluded.stato, assegnatario = excluded.assegnatario,
                 scadenza_lead = excluded.scadenza_lead, veicolo_id = excluded.veicolo_id,
                 file_origine = excluded.file_origine, importato_at = excluded.importato_at""",
            (lead.tcar_id, lead.codice_cm, lead.marca, lead.tipologia, lead.campagna,
             _iso(lead.creazione), _iso(lead.scadenza_lead), lead.stato, lead.assegnatario,
             lead.cognome, lead.nome, lead.email, ", ".join(lead.telefoni), lead.targa,
             lead.telaio, lead.modello, _iso(lead.data_immatricolazione),
             veicolo["id"] if veicolo else None, file_origine, adesso),
        )

    conn.execute(
        "INSERT INTO import_log (file, data_import, righe_lette, veicoli_nuovi, veicoli_aggiornati) VALUES (?, ?, ?, ?, ?)",
        (file_origine, adesso, len(leads), 0, arricchiti),
    )
    conn.commit()
    return {"lead": len(leads), "match": match, "arricchiti": arricchiti}


def importa_immatricolazioni(conn: sqlite3.Connection, righe, file_origine: str) -> dict:
    """Aggiorna le date di immatricolazione (fonte autorevole: registro del
    collega). Match per telaio, poi targa, poi cliente+marca (candidato unico).

    Regole date: sovrascrive stimata/mese_report/storico/data_garanzia, non
    tocca tcar/manuale. Le divergenze con data_garanzia/tcar vengono raccolte
    e restituite per il report."""
    esiti = {"righe": 0, "match_telaio": 0, "match_targa": 0, "match_cliente": 0,
             "nuovi": 0, "date_aggiornate": 0, "targhe_aggiunte": 0, "divergenze": []}
    for r in righe:
        esiti["righe"] += 1
        veicolo = None
        if r.telaio:
            veicolo = conn.execute("SELECT * FROM veicoli WHERE telaio = ?", (r.telaio,)).fetchone()
            if veicolo:
                esiti["match_telaio"] += 1
        if veicolo is None and r.targa:
            veicolo = conn.execute("SELECT * FROM veicoli WHERE targa = ?", (r.targa,)).fetchone()
            if veicolo:
                esiti["match_targa"] += 1
        if veicolo is None and r.targa:
            # veicoli del cliente senza targa, di marca compatibile
            marche = MARCHE_EQUIVALENTI.get(r.marca, {r.marca})
            candidati = conn.execute(
                """SELECT v.* FROM veicoli v JOIN clienti c ON c.id = v.cliente_id
                   WHERE c.nome = ? AND IFNULL(v.targa,'') = ''""",
                (r.cliente,),
            ).fetchall()
            candidati = [v for v in candidati if (v["marca"] or "").upper() in marche or not v["marca"]]
            if len(candidati) == 1:
                veicolo = candidati[0]
                esiti["match_cliente"] += 1

        if veicolo is None:
            cliente_id = _trova_o_crea_cliente(conn, r.cliente, None, None)
            conn.execute(
                """INSERT INTO veicoli (telaio, targa, marca, modello, cliente_id,
                   data_immatricolazione, fonte_data, file_origine)
                   VALUES (?, ?, ?, ?, ?, ?, 'immatricolazioni', ?)""",
                (r.telaio or None, r.targa or None, r.marca, r.modello, cliente_id,
                 r.data_immatricolazione.isoformat(), r.file),
            )
            esiti["nuovi"] += 1
            continue

        if r.targa and not veicolo["targa"]:
            conn.execute("UPDATE veicoli SET targa = ? WHERE id = ?", (r.targa, veicolo["id"]))
            esiti["targhe_aggiunte"] += 1
        fonte_esistente = veicolo["fonte_data"] or "sconosciuta"
        data_esistente = veicolo["data_immatricolazione"]
        nuova = r.data_immatricolazione.isoformat()
        # Divergenza tra fonti "certe": stessa auto, mese diverso.
        if data_esistente and fonte_esistente in ("data_garanzia", "tcar") and data_esistente[:7] != nuova[:7]:
            esiti["divergenze"].append({
                "targa": r.targa or veicolo["targa"] or "", "telaio": veicolo["telaio"] or "",
                "cliente": r.cliente, "data_db": data_esistente, "fonte_db": fonte_esistente,
                "data_immatricolazioni": nuova, "file": r.file,
            })
        if PRIORITA_FONTE["immatricolazioni"] > PRIORITA_FONTE.get(fonte_esistente, -1):
            if data_esistente != nuova or fonte_esistente != "immatricolazioni":
                conn.execute(
                    "UPDATE veicoli SET data_immatricolazione = ?, fonte_data = 'immatricolazioni' WHERE id = ?",
                    (nuova, veicolo["id"]),
                )
                esiti["date_aggiornate"] += 1

    conn.execute(
        "INSERT INTO import_log (file, data_import, righe_lette, veicoli_nuovi, veicoli_aggiornati) VALUES (?, ?, ?, ?, ?)",
        (file_origine, datetime.now().isoformat(timespec="seconds"), esiti["righe"],
         esiti["nuovi"], esiti["date_aggiornate"]),
    )
    conn.commit()
    return esiti


def archivia_pre(conn: sqlite3.Connection, cutoff: str = "2022-01-01", ripristina: bool = False) -> dict:
    """Archivia i veicoli non gestibili: immatricolati prima del cutoff (o senza
    alcuna data) E senza revisioni registrate che permettano di calcolare un
    ciclo. Reversibile con ripristina=True."""
    if ripristina:
        n = conn.execute("SELECT COUNT(*) AS n FROM veicoli WHERE archiviato = 1").fetchone()["n"]
        conn.execute("UPDATE veicoli SET archiviato = 0")
        conn.commit()
        return {"ripristinati": n}
    cur = conn.execute(
        """UPDATE veicoli SET archiviato = 1
           WHERE archiviato = 0
             AND (data_immatricolazione IS NULL OR data_immatricolazione < ?)
             AND NOT EXISTS (SELECT 1 FROM revisioni_effettuate r WHERE r.veicolo_id = veicoli.id)""",
        (cutoff,),
    )
    conn.commit()
    return {"archiviati": cur.rowcount}


def azzera_date_stimate(conn: sqlite3.Connection) -> int:
    """Rimuove le date stimate residue: meglio nessuna data che una sbagliata."""
    n = conn.execute("SELECT COUNT(*) AS n FROM veicoli WHERE fonte_data = 'stimata'").fetchone()["n"]
    conn.execute("UPDATE veicoli SET data_immatricolazione = NULL, fonte_data = 'sconosciuta' WHERE fonte_data = 'stimata'")
    conn.commit()
    return n


def unisci_omonimi(conn: sqlite3.Connection) -> dict:
    """Fonde i clienti duplicati con nome identico.

    Capita quando la stessa persona arriva da file diversi con telefoni
    diversi. Il cliente "principale" è quello con più veicoli attivi (a parità,
    più veicoli, poi il più vecchio); gli altri vengono fusi dentro di lui:
    i veicoli passano al principale, telefono/email mancanti si completano,
    i doppioni si eliminano."""
    gruppi = conn.execute(
        """SELECT nome FROM clienti WHERE nome NOT IN (SELECT nome FROM omonimi_ignorati)
           GROUP BY nome HAVING COUNT(*) > 1"""
    ).fetchall()
    fusi = gruppi_toccati = 0
    for g in gruppi:
        fusi += unisci_gruppo(conn, g["nome"])
        gruppi_toccati += 1
    conn.commit()
    return {"gruppi": gruppi_toccati, "clienti_fusi": fusi}


def _nome_normalizzato(nome: str) -> str:
    import re as re_mod
    return re_mod.sub(r"[^A-Z0-9]", "", (nome or "").upper())


_FORME_SOCIETARIE = {"SRL", "SRLS", "SPA", "SNC", "SAS", "SCARL", "SS", "COOP",
                     "SOC", "DITTA", "FLLI", "SDF", "STP", "ONLUS"}


def _nucleo_nome(nome: str) -> str:
    """Nucleo del nome per accorpare varianti: via punteggiatura e forme
    societarie. "G.F.C. SRL" -> "GFC", "CAMA SRL" -> "CAMA"."""
    import re as re_mod
    testo = re_mod.sub(r"[^A-Z0-9 ]", " ", (nome or "").upper())
    token = [t for t in testo.split() if t not in _FORME_SOCIETARIE]
    return "".join(token)


def gruppi_varianti_flotta(conn: sqlite3.Connection) -> list[dict]:
    """Clienti aziendali/flotte con nomi scritti in modi diversi ma stesso
    nucleo (o nucleo incluso come prefisso). Solo soggetti aziendali: mai
    accorpamenti fuzzy su nomi di persone."""
    import re as re_mod
    ignorate = {r["chiave"] for r in conn.execute("SELECT chiave FROM varianti_ignorate")}
    azienda_re = re_mod.compile(r"\b(SRL|S\.R\.L|SPA|S\.P\.A|SNC|SAS|S\.A\.S|SCARL|COOP|RENTAL|LEASING|NOLEGGIO|SOCIETA|IMPIANTI|SERVICE|AUTO|MOBILITY|BANQUE|COMUNE)\b")
    clienti = conn.execute(
        """SELECT c.id, c.nome, c.telefono, c.flotta,
                  (SELECT COUNT(*) FROM veicoli v WHERE v.cliente_id = c.id AND v.attivo = 1 AND IFNULL(v.archiviato,0) = 0) AS attivi,
                  (SELECT COUNT(*) FROM veicoli v WHERE v.cliente_id = c.id) AS totali
           FROM clienti c"""
    ).fetchall()
    per_nucleo: dict[str, list] = {}
    for c in clienti:
        nucleo = _nucleo_nome(c["nome"])
        if len(nucleo) >= 3:
            per_nucleo.setdefault(nucleo, []).append(c)

    # unisce i nuclei per prefisso (>=5 caratteri) al nucleo più corto
    nuclei = sorted(per_nucleo, key=len)
    assegnazione: dict[str, str] = {}
    for i, corto in enumerate(nuclei):
        if corto in assegnazione:
            continue
        assegnazione[corto] = corto
        if len(corto) < 5:
            continue
        for lungo in nuclei[i + 1:]:
            if lungo.startswith(corto) and lungo not in assegnazione:
                assegnazione[lungo] = corto

    cluster: dict[str, list] = {}
    for nucleo, membri in per_nucleo.items():
        cluster.setdefault(assegnazione.get(nucleo, nucleo), []).extend(membri)

    gruppi = []
    for chiave, membri in cluster.items():
        if len(membri) < 2 or chiave in ignorate:
            continue
        # solo soggetti aziendali o flotte già marcate
        if not any(azienda_re.search(m["nome"]) or m["flotta"] or m["attivi"] >= 4 for m in membri):
            continue
        gruppi.append({
            "chiave": chiave,
            "membri": [{"id": m["id"], "nome": m["nome"], "telefono": m["telefono"] or "",
                        "attivi": m["attivi"], "totali": m["totali"], "flotta": bool(m["flotta"])}
                       for m in sorted(membri, key=lambda x: -x["totali"])],
            "veicoli_totali": sum(m["totali"] for m in membri),
        })
    gruppi.sort(key=lambda g: -g["veicoli_totali"])
    return gruppi


def unisci_clienti(conn: sqlite3.Connection, ids: list[int]) -> int:
    """Fonde più schede cliente in quella con più veicoli. Eredita recapiti
    mancanti e il flag flotta; le schede svuotate si eliminano."""
    membri = [conn.execute(
        """SELECT c.id, c.telefono, c.email, c.flotta,
                  (SELECT COUNT(*) FROM veicoli v WHERE v.cliente_id = c.id) AS totali
           FROM clienti c WHERE c.id = ?""", (i,)).fetchone() for i in ids]
    membri = [m for m in membri if m]
    if len(membri) < 2:
        return 0
    principale = max(membri, key=lambda m: (m["totali"], -m["id"]))
    telefono_princ = principale["telefono"]
    email_princ = principale["email"]
    fusi = 0
    for m in membri:
        if m["id"] == principale["id"]:
            continue
        conn.execute("UPDATE veicoli SET cliente_id = ? WHERE cliente_id = ?", (principale["id"], m["id"]))
        if m["flotta"]:
            conn.execute("UPDATE clienti SET flotta = 1 WHERE id = ?", (principale["id"],))
        conn.execute("DELETE FROM clienti WHERE id = ?", (m["id"],))
        if m["telefono"] and not telefono_princ:
            telefono_princ = m["telefono"]
            conn.execute("UPDATE clienti SET telefono = ? WHERE id = ?", (telefono_princ, principale["id"]))
        if m["email"] and not email_princ:
            email_princ = m["email"]
            conn.execute("UPDATE clienti SET email = ? WHERE id = ?", (email_princ, principale["id"]))
        fusi += 1
    conn.commit()
    return fusi


def ignora_varianti(conn: sqlite3.Connection, chiave: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO varianti_ignorate (chiave, deciso_il) VALUES (?, ?)",
        (chiave, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()


def trova_doppioni_veicoli(conn: sqlite3.Connection) -> list[dict]:
    """Sospetti doppioni: veicolo con solo telaio + veicolo con sola targa,
    nome cliente normalizzato identico, stesso mese di immatricolazione (o data
    mancante da un lato), marca compatibile."""
    ignorati = {r["chiave"] for r in conn.execute("SELECT chiave FROM doppioni_ignorati")}
    # Le flotte sono già fuori da tutte le liste: inutile chiedere decisioni sui loro doppioni.
    veicoli = conn.execute(
        """SELECT v.id, v.telaio, v.targa, v.marca, v.modello, v.data_immatricolazione,
                  v.fonte_data, v.file_origine, c.id AS cliente_id, c.nome, c.telefono
           FROM veicoli v JOIN clienti c ON c.id = v.cliente_id
           WHERE v.attivo = 1 AND IFNULL(v.archiviato, 0) = 0
             AND IFNULL(c.flotta, 0) = 0"""
    ).fetchall()
    per_nome: dict[str, list] = {}
    for v in veicoli:
        per_nome.setdefault(_nome_normalizzato(v["nome"]), []).append(v)

    def marca_compatibile(a, b):
        ma, mb = (a or "").upper(), (b or "").upper()
        if not ma or not mb:
            return True
        for gruppo in MARCHE_EQUIVALENTI.values():
            if ma in gruppo and mb in gruppo:
                return True
        return ma == mb

    coppie = []
    for gruppo in per_nome.values():
        if len(gruppo) < 2:
            continue
        soli_telaio = [v for v in gruppo if v["telaio"] and not v["targa"]]
        sole_targhe = [v for v in gruppo if v["targa"] and not v["telaio"]]

        def compatibili(a, b):
            da, db_ = a["data_immatricolazione"], b["data_immatricolazione"]
            if da and db_ and da[:7] != db_[:7]:
                return False
            return marca_compatibile(a["marca"], b["marca"])

        # Solo accoppiamenti univoci: un telaio che può essere una sola targa
        # e viceversa. I casi ambigui (2 telai x 2 targhe) non si propongono.
        candidati_a = {a["id"]: [b for b in sole_targhe if compatibili(a, b)] for a in soli_telaio}
        candidati_b = {b["id"]: [a for a in soli_telaio if compatibili(a, b)] for b in sole_targhe}
        for a in soli_telaio:
            comp = candidati_a[a["id"]]
            if len(comp) != 1:
                continue
            b = comp[0]
            if len(candidati_b[b["id"]]) != 1:
                continue
            chiave = f"{min(a['id'], b['id'])}-{max(a['id'], b['id'])}"
            if chiave in ignorati:
                continue
            coppie.append({
                "chiave": chiave, "id_telaio": a["id"], "id_targa": b["id"],
                "cliente_a": a["nome"], "cliente_b": b["nome"],
                "telaio": a["telaio"], "targa": b["targa"],
                "modello_a": " ".join(filter(None, [a["marca"], a["modello"]])),
                "modello_b": " ".join(filter(None, [b["marca"], b["modello"]])),
                "imm_a": a["data_immatricolazione"] or "", "imm_b": b["data_immatricolazione"] or "",
                "fonte_a": a["file_origine"] or "", "fonte_b": b["file_origine"] or "",
            })
    return coppie


def unisci_veicoli(conn: sqlite3.Connection, id_telaio: int, id_targa: int) -> None:
    """Fonde due schede dello stesso veicolo: resta quella col telaio, che
    eredita targa, dati migliori e storico dell'altra."""
    a = conn.execute("SELECT * FROM veicoli WHERE id = ?", (id_telaio,)).fetchone()
    b = conn.execute("SELECT * FROM veicoli WHERE id = ?", (id_targa,)).fetchone()
    if not a or not b:
        return
    modifiche = {}
    if b["targa"] and not a["targa"]:
        modifiche["targa"] = b["targa"]
    if b["modello"] and not a["modello"]:
        modifiche["modello"] = b["modello"]
    if b["marca"] and not a["marca"]:
        modifiche["marca"] = b["marca"]
    if b["data_immatricolazione"] and PRIORITA_FONTE.get(b["fonte_data"] or "sconosciuta", -1) > PRIORITA_FONTE.get(a["fonte_data"] or "sconosciuta", -1):
        modifiche["data_immatricolazione"] = b["data_immatricolazione"]
        modifiche["fonte_data"] = b["fonte_data"]
    if modifiche:
        assegnazioni = ", ".join(f"{k} = ?" for k in modifiche)
        conn.execute(f"UPDATE veicoli SET {assegnazioni} WHERE id = ?",
                     (*modifiche.values(), id_telaio))
    # storico dell'altra scheda: revisioni, contatti, lead
    for tabella in ("revisioni_effettuate", "contatti", "lead_tcar", "revisioni_dekra"):
        conn.execute(f"UPDATE {tabella} SET veicolo_id = ? WHERE veicolo_id = ?",
                     (id_telaio, id_targa))
    # cliente: tieni quello col telefono migliore; l'altro, se resta senza veicoli, si elimina
    cliente_a, cliente_b = a["cliente_id"], b["cliente_id"]
    if cliente_a != cliente_b:
        tel_a = conn.execute("SELECT telefono FROM clienti WHERE id = ?", (cliente_a,)).fetchone()["telefono"]
        if not tel_a:
            conn.execute("UPDATE veicoli SET cliente_id = ? WHERE id = ?", (cliente_b, id_telaio))
            cliente_a, cliente_b = cliente_b, cliente_a
        conn.execute("DELETE FROM veicoli WHERE id = ?", (id_targa,))
        resto = conn.execute("SELECT COUNT(*) AS n FROM veicoli WHERE cliente_id = ?", (cliente_b,)).fetchone()["n"]
        if resto == 0:
            conn.execute("DELETE FROM clienti WHERE id = ?", (cliente_b,))
    else:
        conn.execute("DELETE FROM veicoli WHERE id = ?", (id_targa,))
    conn.commit()


def ignora_doppione(conn: sqlite3.Connection, chiave: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO doppioni_ignorati (chiave, deciso_il) VALUES (?, ?)",
        (chiave, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()


def gruppi_omonimi(conn: sqlite3.Connection) -> list[dict]:
    """Gruppi di clienti con nome identico su cui l'operatore deve decidere
    (esclusi quelli già dichiarati 'persone diverse')."""
    nomi = conn.execute(
        """SELECT nome, COUNT(*) AS n FROM clienti
           WHERE nome NOT IN (SELECT nome FROM omonimi_ignorati)
           GROUP BY nome HAVING n > 1 ORDER BY n DESC, nome"""
    ).fetchall()
    gruppi = []
    for r in nomi:
        membri = conn.execute(
            """SELECT c.id, c.telefono, c.email,
                      (SELECT COUNT(*) FROM veicoli v WHERE v.cliente_id = c.id AND v.attivo = 1 AND IFNULL(v.archiviato,0) = 0) AS attivi,
                      (SELECT COUNT(*) FROM veicoli v WHERE v.cliente_id = c.id) AS totali,
                      (SELECT GROUP_CONCAT(IFNULL(v.targa, v.telaio), ', ') FROM veicoli v WHERE v.cliente_id = c.id) AS mezzi
               FROM clienti c WHERE c.nome = ? ORDER BY c.id""",
            (r["nome"],),
        ).fetchall()
        gruppi.append({"nome": r["nome"], "membri": [dict(m) for m in membri]})
    return gruppi


def unisci_gruppo(conn: sqlite3.Connection, nome: str) -> int:
    """Fonde un singolo gruppo di omonimi (stessa logica di unisci_omonimi)."""
    membri = conn.execute(
        """SELECT c.id, c.telefono, c.email, c.flotta,
                  (SELECT COUNT(*) FROM veicoli v WHERE v.cliente_id = c.id AND v.attivo = 1) AS attivi,
                  (SELECT COUNT(*) FROM veicoli v WHERE v.cliente_id = c.id) AS totali
           FROM clienti c WHERE c.nome = ?""",
        (nome,),
    ).fetchall()
    if len(membri) < 2:
        return 0
    principale = max(membri, key=lambda m: (m["attivi"], m["totali"], -m["id"]))
    telefono_princ, email_princ = principale["telefono"], principale["email"]
    fusi = 0
    for m in membri:
        if m["id"] == principale["id"]:
            continue
        conn.execute("UPDATE veicoli SET cliente_id = ? WHERE cliente_id = ?",
                     (principale["id"], m["id"]))
        if m["flotta"]:
            conn.execute("UPDATE clienti SET flotta = 1 WHERE id = ?", (principale["id"],))
        conn.execute("DELETE FROM clienti WHERE id = ?", (m["id"],))
        if m["telefono"] and not telefono_princ:
            telefono_princ = m["telefono"]
            conn.execute("UPDATE clienti SET telefono = ? WHERE id = ?", (telefono_princ, principale["id"]))
        if m["email"] and not email_princ:
            email_princ = m["email"]
            conn.execute("UPDATE clienti SET email = ? WHERE id = ?", (email_princ, principale["id"]))
        fusi += 1
    conn.commit()
    return fusi


def ignora_omonimi(conn: sqlite3.Connection, nome: str) -> None:
    """L'operatore ha stabilito che gli omonimi con questo nome sono persone diverse."""
    conn.execute(
        "INSERT OR REPLACE INTO omonimi_ignorati (nome, deciso_il) VALUES (?, ?)",
        (nome, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()


def candidati_flotta(conn: sqlite3.Connection, soglia: int = 4) -> list[sqlite3.Row]:
    """Clienti con almeno `soglia` veicoli attivi: quasi sempre flotte aziendali."""
    return conn.execute(
        """SELECT c.id, c.nome, c.telefono, c.flotta, COUNT(v.id) AS veicoli
           FROM clienti c JOIN veicoli v ON v.cliente_id = c.id AND v.attivo = 1
           GROUP BY c.id HAVING veicoli >= ? ORDER BY veicoli DESC""",
        (soglia,),
    ).fetchall()


def imposta_flotta(conn: sqlite3.Connection, cliente_id: int, flotta: bool) -> None:
    conn.execute("UPDATE clienti SET flotta = ? WHERE id = ?", (1 if flotta else 0, cliente_id))
    conn.commit()


def trova_punto_vendita(conn: sqlite3.Connection, riferimento: str) -> sqlite3.Row | None:
    """Trova un punto vendita per codice esatto o per pezzo di descrizione (es. "livio")."""
    riferimento = riferimento.strip()
    if riferimento.isdigit():
        return conn.execute(
            "SELECT * FROM punti_vendita WHERE codice = ?", (riferimento.zfill(2),)
        ).fetchone()
    righe = conn.execute(
        "SELECT * FROM punti_vendita WHERE descrizione LIKE ? ORDER BY codice",
        (f"%{riferimento}%",),
    ).fetchall()
    return righe[0] if len(righe) == 1 else None


def imposta_esclusione(conn: sqlite3.Connection, codice: str, escluso: bool) -> None:
    conn.execute(
        "UPDATE punti_vendita SET escluso = ? WHERE codice = ?",
        (1 if escluso else 0, codice),
    )
    conn.commit()


def elenca_punti_vendita(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT pv.codice, pv.descrizione, pv.escluso, COUNT(v.id) AS veicoli
           FROM punti_vendita pv LEFT JOIN veicoli v ON v.punto_vendita = pv.codice
           GROUP BY pv.codice ORDER BY pv.codice"""
    ).fetchall()


def aggiungi_a_coda(conn: sqlite3.Connection, veicolo_ids: list[int], canale: str,
                    scadenze: dict[int, str]) -> int:
    """Mette i veicoli selezionati in coda d'invio (sms|brevo). Chi è già in
    coda per lo stesso canale senza invio effettuato non viene duplicato."""
    adesso = datetime.now().isoformat(timespec="seconds")
    aggiunti = 0
    for vid in veicolo_ids:
        gia = conn.execute(
            "SELECT 1 FROM code_invio WHERE veicolo_id = ? AND canale = ? AND inviato_il IS NULL",
            (vid, canale),
        ).fetchone()
        if gia:
            continue
        conn.execute(
            "INSERT INTO code_invio (veicolo_id, canale, scadenza, aggiunto_il) VALUES (?, ?, ?, ?)",
            (vid, canale, scadenze.get(vid, ""), adesso),
        )
        aggiunti += 1
    conn.commit()
    return aggiunti


def coda_invio(conn: sqlite3.Connection, canale: str, solo_in_coda: bool = True) -> list[sqlite3.Row]:
    filtro = "AND q.inviato_il IS NULL" if solo_in_coda else ""
    return conn.execute(f"""
        SELECT q.id, q.veicolo_id, q.scadenza, q.aggiunto_il, q.inviato_il,
               c.nome AS cliente, c.telefono, c.email,
               v.targa, v.telaio, v.marca, v.modello
        FROM code_invio q
        JOIN veicoli v ON v.id = q.veicolo_id
        JOIN clienti c ON c.id = v.cliente_id
        WHERE q.canale = ? {filtro}
        ORDER BY q.inviato_il IS NOT NULL, q.aggiunto_il DESC""", (canale,)).fetchall()


def rimuovi_da_coda(conn: sqlite3.Connection, coda_id: int) -> None:
    conn.execute("DELETE FROM code_invio WHERE id = ? AND inviato_il IS NULL", (coda_id,))
    conn.commit()


def svuota_coda(conn: sqlite3.Connection, canale: str) -> int:
    """Svuota la coda del canale (solo le voci non inviate; lo storico resta)."""
    n = conn.execute(
        "DELETE FROM code_invio WHERE canale = ? AND inviato_il IS NULL", (canale,)
    ).rowcount
    conn.commit()
    return n


def segna_coda_inviata(conn: sqlite3.Connection, canale: str) -> int:
    """Marca l'intera coda del canale come inviata oggi e registra l'esito sul
    contatto di ogni veicolo (sms_inviato / email_inviata)."""
    adesso = datetime.now().isoformat(timespec="seconds")
    in_coda = conn.execute(
        "SELECT id, veicolo_id, scadenza FROM code_invio WHERE canale = ? AND inviato_il IS NULL",
        (canale,),
    ).fetchall()
    esito = "sms_inviato" if canale == "sms" else "email_inviata"
    for r in in_coda:
        conn.execute("UPDATE code_invio SET inviato_il = ? WHERE id = ?", (adesso, r["id"]))
        conn.execute(
            "INSERT INTO contatti (veicolo_id, scadenza, data_contatto, esito, note) VALUES (?, ?, ?, ?, ?)",
            (r["veicolo_id"], r["scadenza"] or "", adesso, esito, f"invio bulk {canale}"),
        )
    conn.commit()
    return len(in_coda)


# Tabelle dei dati (non di configurazione dello schema): svuotate dal reset.
TABELLE_DATI = [
    "code_invio", "contatti", "revisioni_effettuate", "revisioni_dekra", "lead_tcar", "veicoli",
    "clienti", "punti_vendita", "import_log",
    "omonimi_ignorati", "doppioni_ignorati", "varianti_ignorate",
]


def svuota_dati(conn: sqlite3.Connection) -> None:
    """Cancella tutti i dati (clienti, veicoli, storico, code, decisioni),
    lasciando intatta la struttura del database."""
    for tabella in TABELLE_DATI:
        conn.execute(f"DELETE FROM {tabella}")
    conn.commit()


def esegui_backup(percorso_db: Path) -> list[str]:
    """Copia di sicurezza del database (una al giorno, tiene le ultime 30).

    Destinazioni: dati/backup accanto al database e, se esiste il file
    dati/backup_percorso.txt, anche il percorso lì indicato (es. la cartella
    condivisa aziendale). Usa l'API di backup di SQLite: copia consistente
    anche a programma acceso."""
    from datetime import date as date_mod
    esiti = []
    if not percorso_db.exists():
        return esiti
    destinazioni = [percorso_db.parent / "backup"]
    config = percorso_db.parent / "backup_percorso.txt"
    if config.exists():
        extra = Path(config.read_text(encoding="utf-8").strip().strip('"'))
        if str(extra):
            destinazioni.append(extra)
    nome = f"revisioni_{date_mod.today().strftime('%Y%m%d')}.db"
    sorgente = sqlite3.connect(percorso_db)
    try:
        for cartella in destinazioni:
            try:
                cartella.mkdir(parents=True, exist_ok=True)
                destinazione_file = cartella / nome
                if destinazione_file.exists():
                    esiti.append(f"{cartella}: già fatto oggi")
                    continue
                dest = sqlite3.connect(destinazione_file)
                with dest:
                    sorgente.backup(dest)
                dest.close()
                # tieni solo gli ultimi 30 backup
                vecchi = sorted(cartella.glob("revisioni_*.db"))[:-30]
                for v in vecchi:
                    v.unlink(missing_ok=True)
                esiti.append(f"{cartella}: ok")
            except Exception as e:
                esiti.append(f"{cartella}: ERRORE {str(e)[:60]}")
    finally:
        sorgente.close()
    return esiti


def registra_contatto(conn: sqlite3.Connection, veicolo_id: int, scadenza: str, esito: str, note: str = "") -> None:
    conn.execute(
        "INSERT INTO contatti (veicolo_id, scadenza, data_contatto, esito, note) VALUES (?, ?, ?, ?, ?)",
        (veicolo_id, scadenza, datetime.now().isoformat(timespec="seconds"), esito, note),
    )
    conn.commit()


def registra_revisione(conn: sqlite3.Connection, veicolo_id: int, data_revisione: date, fonte: str = "operatore") -> None:
    """Registra una revisione effettuata: la prossima scadenza slitta a +2 anni.
    Se il veicolo era archiviato per mancanza di dati, ora il dato c'è: rientra."""
    conn.execute(
        "INSERT INTO revisioni_effettuate (veicolo_id, data_revisione, fonte) VALUES (?, ?, ?)",
        (veicolo_id, data_revisione.isoformat(), fonte),
    )
    conn.execute("UPDATE veicoli SET archiviato = 0 WHERE id = ?", (veicolo_id,))
    conn.commit()


def dismetti_veicolo(conn: sqlite3.Connection, veicolo_id: int) -> None:
    """Il cliente non possiede più il veicolo: esce da scadenzario e liste."""
    conn.execute("UPDATE veicoli SET attivo = 0 WHERE id = ?", (veicolo_id,))
    conn.commit()


def inserisci_veicolo_manuale(conn: sqlite3.Connection, cliente_id: int, targa: str | None,
                              telaio: str | None, marca: str, modello: str,
                              data_immatricolazione: date | None) -> int:
    """Inserisce un veicolo comunicato a voce dal cliente (fonte 'manuale')."""
    veicolo_id = conn.execute(
        """INSERT INTO veicoli (telaio, targa, marca, modello, cliente_id,
           data_immatricolazione, fonte_data, file_origine)
           VALUES (?, ?, ?, ?, ?, ?, 'manuale', 'inserimento manuale')""",
        (telaio or None, targa or None, marca, modello, cliente_id,
         _iso(data_immatricolazione)),
    ).lastrowid
    conn.commit()
    return veicolo_id


def clienti_senza_veicolo(conn: sqlite3.Connection) -> list[dict]:
    """Clienti storici rimasti senza veicolo attivo: da richiamare per capire
    che auto guidano ora — restiamo il loro fornitore di revisione.

    Ogni riga include motivo, data e fonte della dismissione dell'ultimo veicolo."""
    import re as re_mod
    righe = conn.execute("""
        SELECT c.id, c.nome, c.telefono, c.email,
               uv.marca AS v_marca, uv.modello AS v_modello,
               uv.targa AS v_targa, uv.telaio AS v_telaio,
               (SELECT k.esito || CHAR(31) || k.data_contatto || CHAR(31) || IFNULL(k.note,'')
                FROM contatti k JOIN veicoli v2 ON v2.id = k.veicolo_id
                WHERE v2.cliente_id = c.id
                  AND k.esito IN ('VENDUTA','AUTO VENDUTA','DEMOLITA','RUBATA','non_possiede_piu')
                ORDER BY k.data_contatto DESC LIMIT 1) AS dismissione
        FROM clienti c
        LEFT JOIN veicoli uv ON uv.id = (
            SELECT v3.id FROM veicoli v3 WHERE v3.cliente_id = c.id ORDER BY v3.id DESC LIMIT 1)
        WHERE EXISTS (SELECT 1 FROM veicoli v WHERE v.cliente_id = c.id AND IFNULL(v.archiviato,0) = 0)
          AND NOT EXISTS (SELECT 1 FROM veicoli v WHERE v.cliente_id = c.id AND v.attivo = 1 AND IFNULL(v.archiviato,0) = 0)
        ORDER BY c.nome
    """).fetchall()
    risultati = []
    for r in righe:
        motivo, dismesso_il, fonte = "", "", ""
        if r["dismissione"]:
            esito, data_contatto, note = r["dismissione"].split(chr(31), 2)
            motivo = esito.replace("_", " ").lower()
            dismesso_il = data_contatto[:10]
            m = re_mod.search(r"\[import ([^\]/]+)", note)
            fonte = m.group(1).strip() if m else ("operatore" if esito == "non_possiede_piu" else "")
        # marca/modello a volte coincidono nei dati storici: evita "RENAULT RENAULT"
        marca, modello = (r["v_marca"] or "").strip(), (r["v_modello"] or "").strip()
        veicolo = modello if marca and marca == modello else " ".join(filter(None, [marca, modello]))
        risultati.append({
            "id": r["id"], "nome": r["nome"], "telefono": r["telefono"] or "",
            "email": r["email"] or "",
            "veicolo": veicolo, "targa": r["v_targa"] or "", "telaio": r["v_telaio"] or "",
            "motivo": motivo, "dismesso_il": dismesso_il, "fonte": fonte,
        })
    risultati.sort(key=lambda x: (x["dismesso_il"] == "", x["dismesso_il"]), reverse=False)
    return risultati
