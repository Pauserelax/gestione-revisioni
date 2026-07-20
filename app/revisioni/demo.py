"""Dati fittizi per la demo pubblica.

Nessun dato reale: nomi inventati, telefoni con prefissi di fantasia, email
@example.com (dominio riservato alla documentazione), targhe e telai finti.
Le date sono relative a oggi, così la demo ha sempre scadenze nel mese
corrente, a +1 e +2 mesi, oltre ad arretrato e casi da recuperare.
"""

from __future__ import annotations

import calendar
import sqlite3
from datetime import date

# Nomi di fantasia: cognomi inventati per non coincidere con persone reali.
COGNOMI = [
    "Verdoni", "Castelbianco", "Marlenghi", "Ferruzzo", "Pandolini", "Sarteschi",
    "Beltramini", "Cordifora", "Ravasenga", "Miloni", "Tarpani", "Golfieri",
    "Vestrucci", "Landrini", "Bissoli", "Craveri", "Manzotti", "Perlasca",
    "Zaffiroli", "Ughetti", "Basciano", "Dellera", "Ronchetti", "Salvioni",
]
NOMI = [
    "Marco", "Giulia", "Andrea", "Chiara", "Luca", "Sara", "Davide", "Elena",
    "Matteo", "Federica", "Simone", "Alessia", "Roberto", "Martina", "Paolo",
    "Valentina", "Stefano", "Ilaria", "Fabio", "Anna", "Riccardo", "Laura",
]
MODELLI = [
    ("DACIA", "SANDERO"), ("DACIA", "DUSTER"), ("DACIA", "SPRING"),
    ("DACIA", "JOGGER"), ("RENAULT", "CLIO"), ("RENAULT", "CAPTUR"),
    ("RENAULT", "TWINGO"), ("RENAULT", "MEGANE"), ("RENAULT", "ARKANA"),
]
LETTERE = "ABCDEFGHJKLMNPRSTVWXYZ"


def _fine_mese(anno: int, mese: int) -> date:
    return date(anno, mese, calendar.monthrange(anno, mese)[1])


def _targa(i: int) -> str:
    a = LETTERE[i % len(LETTERE)]
    b = LETTERE[(i // 7) % len(LETTERE)]
    c = LETTERE[(i // 3) % len(LETTERE)]
    d = LETTERE[(i // 5) % len(LETTERE)]
    return f"{a}{b}{100 + (i * 37) % 900}{c}{d}"


def _telaio(i: int) -> str:
    base = "VF1DEMO00000"
    n = f"{(i * 8161) % 100000:05d}"
    return (base + n)[:17]


def _telefono(i: int) -> str:
    # Cellulare finto valido (10 cifre, prefisso 3xx di fantasia), cifre varie.
    coda = f"{(i * 733 + 1009) % 10000000:07d}"
    return "34" + str(3 + i % 6) + coda[:7]


def _immatricolazione(oggi: date, mesi_offset: int) -> date:
    """Immatricolazione tale che (imm + 4 anni) cada `mesi_offset` mesi da oggi."""
    m = oggi.month + mesi_offset
    anno = oggi.year - 4 + (m - 1) // 12
    mese = (m - 1) % 12 + 1
    return date(anno, mese, min(15, calendar.monthrange(anno, mese)[1]))


def carica(conn: sqlite3.Connection, oggi: date | None = None) -> dict:
    oggi = oggi or date.today()

    def cliente(nome: str, telefono: str | None, email: str | None = None, flotta: int = 0) -> int:
        return conn.execute(
            "INSERT INTO clienti (nome, telefono, email, flotta) VALUES (?, ?, ?, ?)",
            (nome, telefono, email, flotta),
        ).lastrowid

    def veicolo(cliente_id: int, i: int, imm: date | None, fonte: str = "immatricolazioni",
                marca_modello=None, targa=None, telaio=None, pv=None) -> int:
        marca, modello = marca_modello or MODELLI[i % len(MODELLI)]
        return conn.execute(
            """INSERT INTO veicoli (telaio, targa, marca, modello, cliente_id,
               data_immatricolazione, fonte_data, punto_vendita, file_origine)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'demo')""",
            (telaio if telaio is not None else _telaio(i),
             targa if targa is not None else _targa(i),
             marca, modello, cliente_id,
             imm.isoformat() if imm else None, fonte, pv),
        ).lastrowid

    i = 0
    # Punti vendita (uno è un segnalatore da escludere nella demo)
    conn.execute("INSERT OR IGNORE INTO punti_vendita (codice, descrizione, escluso) VALUES ('01', 'SEDE', 0)")
    conn.execute("INSERT OR IGNORE INTO punti_vendita (codice, descrizione, escluso) VALUES ('09', 'AUTO PARTNER (segnalatore)', 0)")

    # Scadenze distribuite: mese corrente (0), +1, +2, futuro (+5), arretrato (-8, -30)
    piano = [(0, 14), (1, 8), (2, 6), (5, 5), (-8, 6), (-30, 5)]
    for offset, quanti in piano:
        for _ in range(quanti):
            nome = f"{COGNOMI[i % len(COGNOMI)]} {NOMI[i % len(NOMI)]}"
            tel = _telefono(i)
            email = f"{NOMI[i % len(NOMI)].lower()}.{COGNOMI[i % len(COGNOMI)].lower()}@example.com" if i % 3 else None
            cid = cliente(nome, tel, email)
            veicolo(cid, i, _immatricolazione(oggi, offset))
            i += 1

    # Due telefoni "sporchi" per mostrare il validatore
    cid = cliente(f"{COGNOMI[i % len(COGNOMI)]} Nadia", "0299999999")  # riempitivo
    veicolo(cid, i, _immatricolazione(oggi, 0)); i += 1
    cid = cliente(f"{COGNOMI[i % len(COGNOMI)]} Bruno", "3331234")     # troppo corto
    veicolo(cid, i, _immatricolazione(oggi, 1)); i += 1

    # Una flotta (azienda con più veicoli, esclusa dalle liste)
    fid = cliente("VERDONI TRASPORTI SRL", "0331700700", flotta=1)
    for _ in range(5):
        veicolo(fid, i, _immatricolazione(oggi, i % 3)); i += 1

    # Omonimi da decidere (due schede stesso nome, telefoni diversi)
    a = cliente("ROSSI MARIO", "3480010203")
    veicolo(a, i, _immatricolazione(oggi, 0)); i += 1
    b = cliente("ROSSI MARIO", "3480099887")
    veicolo(b, i, _immatricolazione(oggi, 2)); i += 1

    # Cliente da recuperare: unico veicolo venduto
    rid = cliente("MARLENGHI Ester", "3479988776")
    vid = veicolo(rid, i, _immatricolazione(oggi, -6)); i += 1
    conn.execute("UPDATE veicoli SET attivo = 0 WHERE id = ?", (vid,))
    conn.execute(
        "INSERT INTO contatti (veicolo_id, scadenza, data_contatto, esito, note) VALUES (?, '', ?, 'VENDUTA', '[import demo]')",
        (vid, oggi.isoformat()),
    )

    # Un paio di revisioni già effettuate (ciclo che riparte a +2 anni)
    for row in conn.execute("SELECT id FROM veicoli WHERE fonte_data = 'immatricolazioni' LIMIT 3").fetchall():
        rev = _fine_mese(oggi.year - 2, oggi.month)
        conn.execute(
            "INSERT INTO revisioni_effettuate (veicolo_id, data_revisione, fonte) VALUES (?, ?, 'demo')",
            (row["id"], rev.isoformat()),
        )

    conn.commit()
    return {
        "clienti": conn.execute("SELECT COUNT(*) AS n FROM clienti").fetchone()["n"],
        "veicoli": conn.execute("SELECT COUNT(*) AS n FROM veicoli").fetchone()["n"],
    }
