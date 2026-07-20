"""Validazione dei numeri di telefono italiani.

Stati possibili:
- cellulare  → valido per SMS e chiamate
- fisso      → valido solo per chiamate
- sospetto   → fittizio o riempitivo (cifre ripetute, sequenze, code di 9/0)
- non_valido → struttura impossibile (lunghezza, prefisso)
- mancante   → campo vuoto
"""

from __future__ import annotations

import re
from functools import lru_cache

ORDINE = {"cellulare": 0, "fisso": 1, "sospetto": 2, "non_valido": 3, "mancante": 4}


def _normalizza(pezzo: str) -> str:
    cifre = re.sub(r"\D", "", pezzo)
    if cifre.startswith("00"):
        cifre = cifre[2:]
    if cifre.startswith("39") and len(cifre) > 10:
        cifre = cifre[2:]
    return cifre


def _sequenza(cifre: str, lunghezza: int = 6) -> bool:
    """True se contiene una sequenza ascendente/discendente di almeno `lunghezza` cifre."""
    for i in range(len(cifre) - lunghezza + 1):
        blocco = cifre[i:i + lunghezza]
        diff = {(int(blocco[j + 1]) - int(blocco[j])) % 10 for j in range(lunghezza - 1)}
        if diff == {1} or diff == {9}:
            return True
    return False


def valuta_numero(pezzo: str) -> tuple[str, str, str]:
    """Valuta un singolo numero: (stato, numero_normalizzato, motivo)."""
    cifre = _normalizza(pezzo)
    if not cifre:
        return "mancante", "", ""
    if len(cifre) < 6:
        return "non_valido", cifre, "troppo corto"
    if len(set(cifre)) <= 2:
        return "sospetto", cifre, "cifre ripetute"
    if _sequenza(cifre):
        return "sospetto", cifre, "sequenza (es. 123456)"
    if len(cifre) >= 8 and len(set(cifre[-6:])) == 1:
        return "sospetto", cifre, "riempitivo (coda di cifre uguali)"
    if cifre.startswith("3"):
        if len(cifre) == 10:
            return "cellulare", cifre, ""
        if len(cifre) == 9:
            return "sospetto", cifre, "cellulare corto: manca una cifra"
        if len(cifre) == 11:
            return "sospetto", cifre, "cellulare con una cifra in più"
        return "non_valido", cifre, f"cellulare di {len(cifre)} cifre"
    if cifre.startswith("0"):
        if 9 <= len(cifre) <= 11:
            return "fisso", cifre, ""
        if len(cifre) == 8:
            return "sospetto", cifre, "fisso corto: possibile cifra mancante"
        return "non_valido", cifre, f"fisso di {len(cifre)} cifre"
    return "non_valido", cifre, "prefisso non italiano"


def valuta_campo(campo: str) -> tuple[str, str, str]:
    """Come _valuta_campo ma con cache: gli stessi numeri ricorrono migliaia di volte."""
    return _valuta_campo(str(campo or ""))


@lru_cache(maxsize=65536)
def _valuta_campo(campo: str) -> tuple[str, str, str]:
    """Valuta un campo che può contenere più numeri: restituisce il migliore.

    (stato, numero, motivo) — preferisce cellulare > fisso > sospetto.
    I numeri possono essere scritti spezzati ("349 7337719", "0331/796500"):
    si valutano sia i singoli gruppi di cifre sia le loro concatenazioni."""
    gruppi = re.findall(r"\d+", str(campo or ""))
    if not gruppi:
        return "mancante", "", "campo vuoto"
    candidati = set(gruppi)
    for i in range(len(gruppi)):
        accumulo = gruppi[i]
        for j in range(i + 1, len(gruppi)):
            accumulo += gruppi[j]
            if len(accumulo) > 14:
                break
            candidati.add(accumulo)
    migliore = ("mancante", "", "campo vuoto")
    for candidato in sorted(candidati, key=len, reverse=True):
        esito = valuta_numero(candidato)
        if ORDINE[esito[0]] < ORDINE[migliore[0]]:
            migliore = esito
    return migliore


def cellulare_valido(campo: str) -> str:
    """Il cellulare valido per SMS, oppure stringa vuota."""
    stato, numero, _ = valuta_campo(campo)
    return numero if stato == "cellulare" else ""


def telefoni_condivisi(conn, minimo_clienti: int = 3) -> list:
    """Numeri usati da più clienti diversi: quasi sempre segnaposto/centralino."""
    return conn.execute(
        """SELECT telefono, COUNT(*) AS n, GROUP_CONCAT(nome, ' | ') AS clienti
           FROM clienti WHERE IFNULL(telefono,'') != ''
           GROUP BY telefono HAVING n >= ? ORDER BY n DESC""",
        (minimo_clienti,),
    ).fetchall()
