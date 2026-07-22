"""Parser dell'export PDF del portale Dekra (linea revisioni in officina).

Il PDF è un elenco tabellare senza intestazioni: progressivo, categoria
(M1/N1/M1G/N1G), targa, telaio, data prenotazione, data accettazione, tipo
operazione (REV, A06…), esito (REGOLARE / SOSPESO (1) / RIPETERE (2) data / ----),
data operazione, data emissione, codice pratica.
Ogni riga è la prova che il veicolo è passato in linea DA NOI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

RIGA_RX = re.compile(
    r"^\s*\d+\s+"
    r"(?P<categoria>[A-Z]\d[A-Z]?)\s+"
    r"(?P<targa>[A-Z0-9]{5,8})\s+"
    r"(?P<telaio>[A-Z0-9]{4,17})\s+"    # anche numeri telaio corti (veicoli d'epoca)
    r"(?P<data1>\d{2}/\d{2}/\d{4}|-{2,})\s+"
    r"(?P<data2>\d{2}/\d{2}/\d{4}|-{2,})\s+"
    r"(?P<tipo>[A-Z][A-Z0-9]{1,3})\s+"
    r"(?P<esito>.+?)\s+"
    r"(?P<data3>\d{2}/\d{2}/\d{4}|-{2,})\s+"
    r"(?P<data4>\d{2}/\d{2}/\d{4}|-{2,})"
    r"(?:\s+(?P<codice>[A-Z0-9]{6,}|-{2,}))?\s*$"
)


@dataclass
class RigaDekra:
    categoria: str
    targa: str
    telaio: str
    tipo_operazione: str        # REV = revisione; altri codici = operazioni diverse
    esito: str                  # REGOLARE | SOSPESO (1) | RIPETERE (2) gg/mm/aaaa | ""
    data_prenotazione: date | None
    data_revisione: date | None  # data emissione (l'ultima colonna data disponibile)
    codice_pratica: str | None

    @property
    def regolare(self) -> bool:
        return self.esito.startswith("REGOLARE")


def _data(testo: str | None) -> date | None:
    if not testo or set(testo) == {"-"}:
        return None
    try:
        return datetime.strptime(testo, "%d/%m/%Y").date()
    except ValueError:
        return None


def _pagine_testo(percorso: Path):
    """Testo pagina per pagina: pypdf (nel pacchetto Windows) o pdfplumber."""
    try:
        from pypdf import PdfReader
    except ImportError:
        import pdfplumber
        with pdfplumber.open(percorso) as pdf:
            for pagina in pdf.pages:
                yield pagina.extract_text(layout=True) or ""
        return
    for pagina in PdfReader(percorso).pages:
        yield pagina.extract_text(extraction_mode="layout") or ""


def leggi_pdf_dekra(percorso: Path) -> list[RigaDekra]:
    """Estrae le righe revisione dal PDF Dekra."""
    righe: list[RigaDekra] = []
    for testo in _pagine_testo(percorso):
        for linea in testo.splitlines():
            m = RIGA_RX.match(linea)
            if not m:
                continue
            esito = m["esito"].strip()
            if set(esito) == {"-"}:
                esito = ""
            codice = m["codice"]
            if codice and set(codice) == {"-"}:
                codice = None
            data_rev = _data(m["data4"]) or _data(m["data3"]) or _data(m["data1"])
            righe.append(RigaDekra(
                categoria=m["categoria"],
                targa=m["targa"],
                telaio=m["telaio"],
                tipo_operazione=m["tipo"],
                esito=esito,
                data_prenotazione=_data(m["data1"]),
                data_revisione=data_rev,
                codice_pratica=codice,
            ))
    return righe


def trova_file_dekra(cartella: Path) -> list[Path]:
    """PDF nella cartella indicata (non ricorsivo: altrove ci sono PDF di pratiche)."""
    return sorted(p for p in cartella.glob("*.pdf") if not p.name.startswith("~"))
