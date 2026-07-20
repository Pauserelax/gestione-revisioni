"""Parser dell'export lead di Tcar ("EstrazioneLeads*.xlsx").

Il file è una tabella con intestazioni in prima riga; le colonne vengono
riconosciute per nome, quindi l'ordine può cambiare tra estrazioni.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import openpyxl

VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")


@dataclass
class LeadTcar:
    tcar_id: int
    codice_cm: str
    marca: str
    tipologia: str
    campagna: str
    creazione: date | None
    scadenza_lead: date | None
    stato: str
    assegnatario: str
    cognome: str
    nome: str
    email: str
    telefoni: list[str] = field(default_factory=list)
    targa: str = ""
    telaio: str = ""
    modello: str = ""
    data_immatricolazione: date | None = None


def _testo(riga: dict, colonna: str) -> str:
    v = riga.get(colonna)
    return str(v).strip() if v is not None else ""


def _data(riga: dict, colonna: str) -> date | None:
    v = riga.get(colonna)
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return None


def leggi_export_lead(percorso: Path) -> list[LeadTcar]:
    wb = openpyxl.load_workbook(percorso, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    righe = ws.iter_rows(values_only=True)
    intestazioni = [str(c).strip() if c is not None else "" for c in next(righe)]

    leads: list[LeadTcar] = []
    for valori in righe:
        if not any(valori):
            continue
        r = dict(zip(intestazioni, valori))
        if not r.get("ID"):
            continue
        telaio = _testo(r, "VP - Telaio").upper()
        if not VIN_RE.match(telaio):
            telaio = ""
        telefoni = []
        for col in ("Cellulare", "Cellulare2", "Telefono", "Telefono2"):
            t = _testo(r, col)
            if t and t not in telefoni:
                telefoni.append(t)
        leads.append(LeadTcar(
            tcar_id=int(r["ID"]),
            codice_cm=_testo(r, "Codice C.M."),
            marca=_testo(r, "Marca"),
            tipologia=_testo(r, "Tipologia"),
            campagna=_testo(r, "Campagna"),
            creazione=_data(r, "Creazione"),
            scadenza_lead=_data(r, "Scadenza"),
            stato=_testo(r, "Stato comm."),
            assegnatario=_testo(r, "Assegnatario"),
            cognome=_testo(r, "Cognome/R.S."),
            nome=_testo(r, "Nome"),
            email=_testo(r, "Email") or _testo(r, "Email2"),
            telefoni=telefoni,
            targa=_testo(r, "VP - Targa").upper(),
            telaio=telaio,
            modello=_testo(r, "VP - Modello"),
            data_immatricolazione=_data(r, "VP - Data Imm."),
        ))
    wb.close()
    return leads
