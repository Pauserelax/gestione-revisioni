"""Parser del report WinDrakkar "RIEPILOGO MENSILE C.C.F." esportato in Excel.

Il report è una stampa testuale a colonne fisse riversata in un foglio Excel:
la colonna A contiene le intestazioni di pagina, la colonna B le righe del
tabulato. Ogni riga veicolo contiene punto vendita, marca, modello, versione,
serie, telaio, data garanzia (facoltativa), ragione sociale, telefono, dati
ordine e listino.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import openpyxl

VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
DATA_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
PUNTO_VENDITA_RE = re.compile(r"Punto Vendita\s*:\s*(\d+)\s*(.*)")

# Posizioni (0-based) delle colonne del tabulato, misurate sul tracciato reale.
SLICES = {
    "punto_vendita": (1, 7),
    "marca": (7, 12),
    "modello": (12, 16),
    "versione": (16, 20),
    "serie": (20, 25),
    "telaio": (25, 45),
    "data_garanzia": (45, 59),
    "ragione_sociale": (59, 89),
    "telefono": (89, 108),
    "anno_ordine": (108, 110),
    "numero_ordine": (110, 118),
    "tipo_contratto": (118, 124),
    "data_ordine": (124, 134),
    "usati": (134, 140),
    "ritiro": (140, 145),
    "documento_acquisto": (145, 155),
    "data_acquisto": (155, 184),
    "listino": (184, 220),
}

MESI_IT = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}


@dataclass
class RigaVeicolo:
    punto_vendita: str
    marca: str
    modello: str
    versione: str
    serie: str
    telaio: str
    data_garanzia: date | None
    ragione_sociale: str
    telefono: str
    anno_ordine: str
    numero_ordine: str
    tipo_contratto: str
    data_ordine: date | None
    documento_acquisto: str
    data_acquisto: date | None
    listino: str
    # Data di riferimento per il calcolo revisione e come è stata determinata.
    data_riferimento: date | None = None
    fonte_data: str = ""


def _parse_data(testo: str) -> date | None:
    testo = testo.strip()
    if not DATA_RE.match(testo):
        return None
    g, m, a = testo.split("/")
    try:
        return date(int(a), int(m), int(g))
    except ValueError:
        return None


def _campo(riga: str, nome: str) -> str:
    i, j = SLICES[nome]
    return riga[i:j].strip()


def mese_da_nome_file(percorso: Path) -> date | None:
    """Estrae mese/anno dal nome file (es. "..._luglio 2022.xlsx") come fine mese."""
    nome = percorso.stem.lower()
    m = re.search(r"(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s*[_ ]\s*(\d{4})", nome)
    if not m:
        return None
    mese = MESI_IT[m.group(1)]
    anno = int(m.group(2))
    return date(anno, mese, calendar.monthrange(anno, mese)[1])


def leggi_report_ccf(percorso: Path) -> tuple[list[RigaVeicolo], dict[str, str]]:
    """Legge il file Excel del riepilogo mensile C.C.F.

    Restituisce le righe veicolo e la mappa codice → descrizione dei punti
    vendita (venditori) trovati nelle intestazioni di pagina.
    """
    wb = openpyxl.load_workbook(percorso, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    fine_mese_report = mese_da_nome_file(percorso)

    veicoli: list[RigaVeicolo] = []
    punti_vendita: dict[str, str] = {}
    for row in ws.iter_rows(values_only=True):
        intestazione = row[0] if row else None
        if isinstance(intestazione, str):
            m = PUNTO_VENDITA_RE.search(intestazione)
            if m:
                codice = m.group(1).zfill(2)
                descrizione = re.sub(r"\s{2,}", " ", m.group(2).strip())
                # Non sovrascrivere una descrizione già trovata con una vuota.
                if descrizione or codice not in punti_vendita:
                    punti_vendita[codice] = descrizione

        testo = row[1] if len(row) > 1 else None
        if not isinstance(testo, str):
            continue
        telaio = _campo(testo, "telaio")
        if not VIN_RE.match(telaio):
            continue

        data_garanzia = _parse_data(_campo(testo, "data_garanzia"))
        data_acquisto = _parse_data(_campo(testo, "data_acquisto"))
        if data_garanzia:
            data_rif, fonte = data_garanzia, "data_garanzia"
        elif fine_mese_report:
            data_rif, fonte = fine_mese_report, "mese_report"
        elif data_acquisto:
            # Stima: la consegna avviene di norma poco dopo la fattura d'acquisto.
            data_rif, fonte = data_acquisto, "stimata"
        else:
            data_rif, fonte = None, "sconosciuta"

        from .modelli import normalizza_marca, normalizza_modello
        veicoli.append(RigaVeicolo(
            punto_vendita=_campo(testo, "punto_vendita"),
            marca=normalizza_marca(_campo(testo, "marca")),
            modello=normalizza_modello(_campo(testo, "modello")),
            versione=_campo(testo, "versione"),
            serie=_campo(testo, "serie"),
            telaio=telaio,
            data_garanzia=data_garanzia,
            ragione_sociale=re.sub(r"\s{2,}", " ", _campo(testo, "ragione_sociale")),
            telefono=_campo(testo, "telefono"),
            anno_ordine=_campo(testo, "anno_ordine"),
            numero_ordine=_campo(testo, "numero_ordine"),
            tipo_contratto=_campo(testo, "tipo_contratto"),
            data_ordine=_parse_data(_campo(testo, "data_ordine")),
            documento_acquisto=_campo(testo, "documento_acquisto"),
            data_acquisto=_parse_data(_campo(testo, "data_acquisto")),
            listino=_campo(testo, "listino"),
            data_riferimento=data_rif,
            fonte_data=fonte,
        ))
    wb.close()
    return veicoli, punti_vendita
