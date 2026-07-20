"""Conversione dei codici interni WinDrakkar in nomi commerciali."""

from __future__ import annotations

MARCHE_CODICI = {"RE": "RENAULT", "R1": "RENAULT", "DC": "DACIA"}

# Corrispondenze confermate dai listini Renault/Dacia (screenshot utente, 17/07/2026).
MODELLI_CODICI = {
    # Dacia
    "BI1": "SANDERO", "S2B": "SANDERO", "JD1": "DUSTER", "DU3": "DUSTER",
    "S1E": "SPRING", "S2E": "SPRING", "RI1": "JOGGER", "BD1": "BIGSTER",
    "52K": "LOGAN MCV", "67P": "DOKKER", "92J": "LODGY",
    # Renault
    "CL5": "CLIO", "CL6": "CLIO", "CP1": "CAPTUR", "AR1": "SYMBIOZ",
    "2WE": "TWINGO", "2W3": "TWINGO", "TWE": "TWINGO", "TWZ": "TWIZY",
    "ZO1": "MEGANE E-TECH", "MK4": "MEGANE", "ZH1": "SCENIC",
    "TRP": "TRAFIC", "HN1": "AUSTRAL", "JL1": "ARKANA", "DN1": "RAFALE",
    "RN1": "ESPACE", "SP5": "ESPACE", "KK1": "KANGOO",
    "R5E": "RENAULT 5", "R 5": "RENAULT 5", "A4E": "RENAULT 4",
}


def normalizza_marca(marca: str) -> str:
    m = (marca or "").strip().upper()
    return MARCHE_CODICI.get(m, m)


def normalizza_modello(modello: str) -> str:
    m = (modello or "").strip().upper()
    return MODELLI_CODICI.get(m, m)
