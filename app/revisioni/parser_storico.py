"""Parser universale dei file storici di lavoro (formato "Cristina").

Legge .xlsx e .xls con tracciati variabili ma colonne riconoscibili dal nome
dell'intestazione: Telaio, Cliente/Ragione Sociale, Targa, Telefono/i, Email,
Data Imm., Modello, Marca, Feedback, Note, Ultima Revisione, Scadenza.
Scandisce tutti i fogli di ogni file e individua da sé la riga di intestazione.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
TARGA_RE = re.compile(r"^[A-Z]{2}\s?\d{3,4}\s?[A-Z]{2}$")

# nome canonico -> possibili intestazioni (confronto in minuscolo, senza spazi doppi)
COLONNE = {
    "telaio": ("telaio",),
    "cliente": ("cliente", "ragione sociale", "cognome/r.s.", "nominativo"),
    "targa": ("targa",),
    "telefono": ("telefono", "tel", "cellulare"),
    "telefono2": ("telefono2", "telefono 2", "cellulare2"),
    "email": ("email", "e-mail", "mail"),
    "data_imm": ("data imm. vn", "data imm.", "data imm", "data immatricolazione", "data immatric", "immatricolazione", "1 imm", "prima imm"),
    "modello": ("modello", "modello/versione"),
    "marca": ("marca",),
    "feedback": ("feedback", "note lead", "esito"),
    "note": ("note", "note "),
    "ultima_revisione": ("ultima revisione", "ultima revisione ", "ultima rev"),
    "scadenza": ("scadenza", "scadenza ", "scad.rev.", "scad rev", "scadenza revisione", "revisione"),
    "tagliando_eseguito": ("tagliando eseguito",),
}


@dataclass
class RigaStorica:
    telaio: str = ""
    targa: str = ""
    cliente: str = ""
    telefoni: list[str] = field(default_factory=list)
    email: str = ""
    marca: str = ""
    modello: str = ""
    data_immatricolazione: date | None = None
    ultima_revisione: date | None = None
    scadenza_dichiarata: date | None = None
    feedback: str = ""
    note: str = ""
    foglio: str = ""


def _pulisci(testo) -> str:
    if testo is None:
        return ""
    return re.sub(r"\s{2,}", " ", str(testo)).strip()


def _parse_data(valore) -> date | None:
    """Interpreta date nei formati visti nei file: datetime, dd/mm/yyyy,
    yyyy-mm(-dd), mm/dd/yyyy (fogli usato di Cristina), 'Mar-26'."""
    if valore is None:
        return None
    if isinstance(valore, datetime):
        return valore.date()
    if isinstance(valore, date):
        return valore
    testo = str(valore).strip()
    if not testo or testo.upper() in ("ND", "#N/A", "#REF!"):
        return None
    testo = testo.split()[0]
    m = re.match(r"^(\d{4})-(\d{1,2})(?:-(\d{1,2}))?$", testo)
    if m:
        a, me = int(m.group(1)), int(m.group(2))
        g = int(m.group(3)) if m.group(3) else calendar.monthrange(a, me)[1]
        return _data_sicura(a, me, g)
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$", testo)
    if m:
        p1, p2, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a < 100:
            a += 2000
        # dd/mm oppure mm/dd: decide chi può essere un mese
        if p1 > 12 and p2 <= 12:
            return _data_sicura(a, p2, p1)
        if p2 > 12 and p1 <= 12:
            return _data_sicura(a, p1, p2)
        return _data_sicura(a, p2, p1)  # ambiguo: prevale l'ordine italiano gg/mm
    mesi = {"gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "may": 5, "giu": 6, "jun": 6,
            "lug": 7, "jul": 7, "ago": 8, "aug": 8, "set": 9, "sep": 9, "ott": 10, "oct": 10,
            "nov": 11, "dic": 12, "dec": 12}
    m = re.match(r"^([A-Za-z]{3})[a-z]*-(\d{2,4})$", testo)
    if m and m.group(1).lower()[:3] in mesi:
        a = int(m.group(2))
        if a < 100:
            a += 2000
        me = mesi[m.group(1).lower()[:3]]
        return date(a, me, calendar.monthrange(a, me)[1])
    return None


def _data_sicura(a: int, m: int, g: int) -> date | None:
    try:
        return date(a, m, g)
    except ValueError:
        return None


def _mappa_intestazioni(riga) -> dict[str, int] | None:
    """Riconosce una riga di intestazione e restituisce nome_canonico -> indice."""
    mappa: dict[str, int] = {}
    for i, cella in enumerate(riga):
        nome = _pulisci(cella).lower()
        if not nome:
            continue
        for canonico, alias in COLONNE.items():
            if canonico not in mappa and nome in alias:
                mappa[canonico] = i
                break
    if "telaio" in mappa or ("targa" in mappa and "cliente" in mappa):
        return mappa
    return None


def _righe_foglio(nome_foglio: str, righe) -> list[RigaStorica]:
    risultati: list[RigaStorica] = []
    mappa: dict[str, int] | None = None
    for riga in righe:
        nuova_mappa = _mappa_intestazioni(riga)
        if nuova_mappa:
            mappa = nuova_mappa
            continue
        if not mappa:
            continue

        def campo(nome):
            i = mappa.get(nome)
            return riga[i] if i is not None and i < len(riga) else None

        telaio = _pulisci(campo("telaio")).upper()
        if not VIN_RE.match(telaio):
            telaio = ""
        targa = _pulisci(campo("targa")).upper().replace(" ", "")
        if not TARGA_RE.match(targa):
            targa = ""
        cliente = _pulisci(campo("cliente")).upper()
        if not telaio and not targa:
            continue
        if not cliente or cliente in ("ND", "CLIENTE", "RAGIONE SOCIALE"):
            continue

        telefoni = []
        for c in ("telefono", "telefono2"):
            t = _pulisci(campo(c)).replace("_", " ").strip()
            for pezzo in re.split(r"[ /]+", t):
                cifre = re.sub(r"\D", "", pezzo)
                if len(cifre) >= 8 and len(set(cifre)) > 2 and cifre not in telefoni:
                    telefoni.append(cifre)
        email = _pulisci(campo("email")).upper()
        if email in ("ND", "NOMAIL@NO.IT", "NOMAIL@MAIL.IT") or "@" not in email:
            email = ""

        risultati.append(RigaStorica(
            telaio=telaio,
            targa=targa,
            cliente=cliente,
            telefoni=telefoni,
            email=email.lower(),
            marca=_pulisci(campo("marca")).upper(),
            modello=_pulisci(campo("modello")).upper(),
            data_immatricolazione=_parse_data(campo("data_imm")),
            ultima_revisione=_parse_data(campo("ultima_revisione")),
            scadenza_dichiarata=_parse_data(campo("scadenza")),
            feedback=_pulisci(campo("feedback")).upper(),
            note=_pulisci(campo("note")),
            foglio=nome_foglio,
        ))
    return risultati


def leggi_file_storico(percorso: Path) -> list[RigaStorica]:
    """Legge un file .xlsx o .xls e restituisce le righe riconosciute."""
    righe: list[RigaStorica] = []
    if percorso.suffix.lower() == ".xls":
        import xlrd
        wb = xlrd.open_workbook(str(percorso))
        for ws in wb.sheets():
            def genera_righe(foglio):
                for r in range(foglio.nrows):
                    valori = []
                    for c in range(foglio.ncols):
                        v = foglio.cell_value(r, c)
                        if foglio.cell_type(r, c) == xlrd.XL_CELL_DATE:
                            try:
                                v = xlrd.xldate_as_datetime(v, wb.datemode)
                            except Exception:
                                pass
                        valori.append(v)
                    yield tuple(valori)
            righe.extend(_righe_foglio(ws.name, genera_righe(ws)))
    else:
        import openpyxl
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            wb = openpyxl.load_workbook(percorso, data_only=True, read_only=True)
        for ws in wb.worksheets:
            righe.extend(_righe_foglio(ws.title, ws.iter_rows(values_only=True)))
        wb.close()
    return righe


def trova_file_storici(cartella: Path) -> list[Path]:
    return sorted(
        p for p in cartella.rglob("*")
        if p.suffix.lower() in (".xlsx", ".xls")
        and not p.name.startswith("~$")
        and not p.name.startswith(".")
    )
