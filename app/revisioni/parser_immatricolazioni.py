"""Parser dei file immatricolazioni del collega (mese per mese).

Struttura: cartelle per anno, un file al mese ("01 - GENNAIO 2022.xlsx",
"MARZO 2024.xlsx"), fogli per marca (RENAULT/DACIA), colonne riconoscibili:
CLIENTE, TARGA, MARCA, MODELLO, eventuale TELAIO e DATA IMM.
La data di immatricolazione è la colonna DATA IMM. se presente, altrimenti
la fine del mese indicato nel nome del file.
"""

from __future__ import annotations

import calendar
import re
import warnings
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
TARGA_RE = re.compile(r"^[A-Z]{2}\s?\d{3,4}\s?[A-Z]{2}$")
MESI = {"GENNAIO": 1, "FEBBRAIO": 2, "MARZO": 3, "APRILE": 4, "MAGGIO": 5, "GIUGNO": 6,
        "LUGLIO": 7, "AGOSTO": 8, "SETTEMBRE": 9, "OTTOBRE": 10, "NOVEMBRE": 11, "DICEMBRE": 12}


@dataclass
class RigaImmatricolazione:
    cliente: str
    targa: str
    telaio: str
    marca: str
    modello: str
    data_immatricolazione: date
    data_da_colonna: bool     # True se dalla colonna DATA IMM., False se dal nome file
    file: str


def _mese_da_nome(percorso: Path) -> date | None:
    nome = percorso.stem.upper()
    anno = re.search(r"(20\d{2})", nome)
    mese = next((m for m in MESI if m in nome), None)
    if not anno or not mese:
        return None
    a, m = int(anno.group(1)), MESI[mese]
    return date(a, m, calendar.monthrange(a, m)[1])


def _testo(v) -> str:
    return re.sub(r"\s{2,}", " ", str(v)).strip().upper() if v is not None else ""


def leggi_file_immatricolazioni(percorso: Path) -> list[RigaImmatricolazione]:
    import openpyxl
    fine_mese = _mese_da_nome(percorso)
    if fine_mese is None:
        return []
    righe: list[RigaImmatricolazione] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(percorso, data_only=True, read_only=True)
    for ws in wb.worksheets:
        # Si leggono SOLO i fogli marca (scelta dell'utente, 17/07/2026): gli
        # altri (PFU, VO+RWAY, riepiloghi) non alimentano lo scadenzario.
        if not any(m in ws.title.upper() for m in ("RENAULT", "DACIA")):
            continue
        header: dict[str, int] | None = None
        for row in ws.iter_rows(values_only=True):
            vals = [_testo(v) for v in row]
            if "CLIENTE" in vals and ("TARGA" in vals or "TELAIO" in vals):
                header = {n: i for i, n in enumerate(vals) if n}
                continue
            if not header:
                continue

            def campo(nome):
                i = header.get(nome)
                return row[i] if i is not None and i < len(row) else None

            cliente = _testo(campo("CLIENTE"))
            if not cliente or cliente == "CLIENTE":
                continue
            targa = _testo(campo("TARGA")).replace(" ", "")
            telaio = _testo(campo("TELAIO"))
            if not TARGA_RE.match(targa):
                targa = ""
            if not VIN_RE.match(telaio):
                telaio = ""
            if not targa and not telaio:
                continue

            data_imm, da_colonna = fine_mese, False
            v = campo("DATA IMM.")
            if isinstance(v, (datetime, date)):
                data_imm = v.date() if isinstance(v, datetime) else v
                da_colonna = True

            righe.append(RigaImmatricolazione(
                cliente=cliente, targa=targa, telaio=telaio,
                marca=_testo(campo("MARCA")), modello=_testo(campo("MODELLO")),
                data_immatricolazione=data_imm, data_da_colonna=da_colonna,
                file=percorso.name,
            ))
    wb.close()
    return righe


def trova_file(cartella: Path) -> list[Path]:
    return sorted(
        p for p in cartella.rglob("*.xlsx")
        if not p.name.startswith("~$") and not p.name.startswith(".")
    )
