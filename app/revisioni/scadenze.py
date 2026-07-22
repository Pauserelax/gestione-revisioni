"""Motore di calcolo delle scadenze revisione.

Regola di legge (art. 80 CdS): prima revisione entro la fine del mese di prima
immatricolazione + 4 anni, poi ogni 2 anni entro la fine del mese dell'ultima
revisione effettuata.
"""

from __future__ import annotations

import calendar
import sqlite3
from dataclasses import dataclass
from datetime import date

from .telefoni import valuta_campo


@dataclass
class ScadenzaVeicolo:
    veicolo_id: int
    telaio: str
    marca: str
    modello: str
    punto_vendita: str
    cliente: str
    telefono: str
    data_immatricolazione: date | None
    fonte_data: str
    ultima_revisione: date | None
    scadenza: date | None
    giorni_rimanenti: int | None
    stato: str          # SCADUTA | IN_SCADENZA | PROSSIMA | FUTURA | DATA_MANCANTE
    ultimo_esito: str   # esito dell'ultimo contatto registrato per questa scadenza
    targa: str = ""
    lead_tcar: str = ""  # campagna dell'ultimo lead Tcar agganciato al veicolo
    avviso: str = ""     # es. possibile cambio auto: il cliente ha un veicolo più recente
    # Fase del flusso operativo: SMS (+2 mesi) | CHIAMATA (+1 mese) |
    # MESE_CORRENTE | ARRETRATO | FUTURA
    fase: str = ""
    telefono_stato: str = ""   # cellulare | fisso | sospetto | non_valido | mancante
    telefono_motivo: str = ""
    fonte_file: str = ""       # ultimo file di import che ha fornito/aggiornato il veicolo
    mai_contattato: bool = False  # nessun contatto registrato, mai (lista "cold")
    email: str = ""


def fine_mese(anno: int, mese: int) -> date:
    return date(anno, mese, calendar.monthrange(anno, mese)[1])


def prossima_scadenza(immatricolazione: date | None, ultima_revisione: date | None, oggi: date) -> date | None:
    """Prossima revisione dovuta: fine mese di (ultima revisione + 2 anni) oppure
    fine mese di (immatricolazione + 4 anni), poi avanti di 2 anni finché già passata
    di oltre un ciclo (veicoli vecchi mai visti in officina)."""
    if ultima_revisione:
        base = fine_mese(ultima_revisione.year + 2, ultima_revisione.month)
    elif immatricolazione:
        base = fine_mese(immatricolazione.year + 4, immatricolazione.month)
    else:
        return None
    # Se la scadenza è passata da più di 2 anni senza revisioni note, la scadenza
    # "attuale" resta comunque la prima non assolta: il veicolo è fuori regola.
    return base


def classifica(scadenza: date | None, oggi: date, giorni_allarme: int = 60) -> str:
    if scadenza is None:
        return "DATA_MANCANTE"
    delta = (scadenza - oggi).days
    if delta < 0:
        return "SCADUTA"
    if scadenza.year == oggi.year and scadenza.month == oggi.month:
        return "IN_SCADENZA"
    if delta <= giorni_allarme:
        return "PROSSIMA"
    return "FUTURA"


def _parse_iso(testo: str | None) -> date | None:
    return date.fromisoformat(testo) if testo else None


def calcola_scadenze(conn: sqlite3.Connection, oggi: date | None = None, giorni_allarme: int = 60,
                     includi_esclusi: bool = False) -> list[ScadenzaVeicolo]:
    oggi = oggi or date.today()
    query = """
        SELECT v.id, v.telaio, v.targa, v.marca, v.modello, v.punto_vendita,
               v.data_immatricolazione, v.fonte_data, v.cliente_id, v.file_origine,
               c.nome AS cliente, c.telefono, c.email,
               (SELECT MAX(data_revisione) FROM revisioni_effettuate r WHERE r.veicolo_id = v.id) AS ultima_revisione,
               (SELECT campagna FROM lead_tcar l WHERE l.veicolo_id = v.id ORDER BY creazione DESC LIMIT 1) AS lead_tcar
        FROM veicoli v JOIN clienti c ON c.id = v.cliente_id
        LEFT JOIN punti_vendita pv ON pv.codice = v.punto_vendita
        WHERE v.attivo = 1 AND IFNULL(v.archiviato, 0) = 0
    """
    if not includi_esclusi:
        query += " AND IFNULL(pv.escluso, 0) = 0 AND IFNULL(c.flotta, 0) = 0"

    # Per rilevare il "cambio auto": data immatricolazione più recente per cliente
    # su tutto il parco attivo (anche punti vendita esclusi).
    piu_recente: dict[int, str] = {
        r["cliente_id"]: r["max_imm"]
        for r in conn.execute(
            """SELECT cliente_id, MAX(data_immatricolazione) AS max_imm
               FROM veicoli WHERE attivo = 1 AND data_immatricolazione IS NOT NULL
               GROUP BY cliente_id"""
        )
    }
    # Ultimo esito per (veicolo, scadenza) in una sola query.
    ultimo_esito: dict[tuple[int, str], str] = {}
    contattati: set[int] = set()
    for k in conn.execute("SELECT veicolo_id, scadenza, esito FROM contatti ORDER BY data_contatto"):
        ultimo_esito[(k["veicolo_id"], k["scadenza"])] = k["esito"]
        contattati.add(k["veicolo_id"])

    risultati: list[ScadenzaVeicolo] = []
    for row in conn.execute(query):
        imm = _parse_iso(row["data_immatricolazione"])
        ult = _parse_iso(row["ultima_revisione"])
        scad = prossima_scadenza(imm, ult, oggi)
        stato = classifica(scad, oggi, giorni_allarme)
        avviso = ""
        max_imm = piu_recente.get(row["cliente_id"])
        if imm and max_imm and max_imm > imm.isoformat():
            avviso = "possibile cambio auto: il cliente ha un veicolo più recente"
        esito = ultimo_esito.get((row["id"], scad.isoformat() if scad else ""), "")
        fase = ""
        if scad:
            diff_mesi = (scad.year - oggi.year) * 12 + (scad.month - oggi.month)
            if diff_mesi < 0:
                fase = "ARRETRATO"
            else:
                fase = {0: "MESE_CORRENTE", 1: "CHIAMATA", 2: "SMS"}.get(diff_mesi, "FUTURA")
        risultati.append(ScadenzaVeicolo(
            veicolo_id=row["id"],
            telaio=row["telaio"] or "",
            marca=row["marca"],
            modello=row["modello"],
            punto_vendita=row["punto_vendita"],
            cliente=row["cliente"],
            telefono=row["telefono"] or "",
            data_immatricolazione=imm,
            fonte_data=row["fonte_data"] or "",
            ultima_revisione=ult,
            scadenza=scad,
            giorni_rimanenti=(scad - oggi).days if scad else None,
            stato=stato,
            ultimo_esito=esito,
            targa=row["targa"] or "",
            lead_tcar=row["lead_tcar"] or "",
            avviso=avviso,
            fase=fase,
            telefono_stato=(tel_stato := valuta_campo(row["telefono"] or ""))[0],
            telefono_motivo=tel_stato[2],
            fonte_file=row["file_origine"] or "",
            mai_contattato=row["id"] not in contattati,
            email=row["email"] or "",
        ))
    ordine = {"SCADUTA": 0, "IN_SCADENZA": 1, "PROSSIMA": 2, "FUTURA": 3, "DATA_MANCANTE": 4}
    risultati.sort(key=lambda s: (ordine[s.stato], s.scadenza or date.max, s.cliente))
    return risultati


def da_contattare(scadenze: list[ScadenzaVeicolo]) -> list[ScadenzaVeicolo]:
    """Lista operativa: tutte le fasi attive del flusso (SMS +2 mesi,
    chiamata +1 mese, mese corrente, arretrato), esclusi i già gestiti."""
    return [s for s in scadenze
            if s.fase in ("SMS", "CHIAMATA", "MESE_CORRENTE", "ARRETRATO")
            and s.ultimo_esito not in ("appuntamento", "non_interessato")]
