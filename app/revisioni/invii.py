"""Coordinatore degli invii automatici — moduli opzionali email / SMS.

L'app base sa solo *esportare* i file per il caricamento manuale su Brevo e
sul gateway SMS. L'invio automatico è fornito da due moduli aggiuntivi e
indipendenti:

    revisioni.modulo_email   invio email via API Brevo (template transazionale)
    revisioni.modulo_sms     invio SMS via gateway HTTP (es. "SMS Script")

Se un modulo non è installato (file assente), il canale corrispondente resta
semplicemente non disponibile: la dashboard nasconde i pulsanti "Invia ora" e
si continua con l'export manuale. Questo file contiene solo ciò che è condiviso
— il parser della configurazione e gli helper HTTP di libreria standard — più
le funzioni di coordinamento usate dalla dashboard.

Nessuna dipendenza esterna: il pacchetto Windows usa un Python embeddable senza
pip ma con supporto SSL, quindi `urllib.request` verso HTTPS funziona.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

# Endpoint Brevo. La variabile d'ambiente REVISIONI_BREVO_BASE permette ai test
# (o a un ambiente di collaudo) di puntarlo a un server finto.
_BASE_BREVO = os.environ.get("REVISIONI_BREVO_BASE", "https://api.brevo.com")

NOME_FILE_CONFIG = "config_invii.txt"

TEMPLATE_CONFIG = """\
# ==========================================================================
#  CONFIGURAZIONE INVII AUTOMATICI (moduli opzionali: email Brevo + SMS)
#  Righe:  chiave = valore     |     # = commento
#  Questo file NON viene toccato dagli aggiornamenti del programma.
#  ATTENZIONE: contiene password e chiavi API. Se la cartella "dati" e' su
#  una condivisione di rete, limitare l'accesso a chi gestisce gli invii.
#
#  Finche' le chiavi restano vuote i pulsanti "Invia ora" non compaiono e si
#  continua a esportare i file per il caricamento manuale.
# ==========================================================================

# ---- MODULO EMAIL (Brevo) -- app.brevo.com -> SMTP & API -> API Keys ----
brevo_api_key        =
brevo_mittente_email =            # indirizzo verificato in Brevo
brevo_mittente_nome  = Centro Car Cazzaro
brevo_reply_to       =
brevo_template_id    =            # ID del template; segnaposto nel template:
#   {{params.NOME}} {{params.TARGA}} {{params.MARCA}} {{params.MODELLO}}
#   {{params.SCADENZA}} (gg/mm/aaaa)   {{params.MESE}} (es. "ottobre 2026")
#   Il template DEVE includere il link di disiscrizione e i dati del mittente.

# ---- MODULO SMS -- gateway "SMS Script" di SMSBiz (vedi manuale dell'account) ----
sms_url            =
sms_metodo         = GET
sms_param_utente   = user
sms_param_password = pass
sms_param_mittente = sender
sms_param_numero   = numero
sms_param_testo    = testo
sms_utente         =
sms_password       =
sms_mittente       =
sms_ok_contiene    = OK           # stringa nella risposta che indica successo
sms_pausa_ms       = 0
"""


# ---------------------------------------------------------------------------
# Configurazione
# ---------------------------------------------------------------------------

def leggi_config(percorso: Path) -> dict[str, str]:
    """Legge dati/config_invii.txt (righe 'chiave = valore', '#' = commento).
    Se il file non esiste lo crea con il template e restituisce un dict vuoto."""
    if not percorso.exists():
        percorso.parent.mkdir(parents=True, exist_ok=True)
        percorso.write_text(TEMPLATE_CONFIG, encoding="utf-8")
    cfg: dict[str, str] = {}
    for riga in percorso.read_text(encoding="utf-8").splitlines():
        r = riga.split("#", 1)[0].strip()
        if not r or "=" not in r:
            continue
        chiave, _, valore = r.partition("=")
        cfg[chiave.strip().lower()] = valore.strip().strip('"').strip("'")
    return cfg


_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _valida_email(email: str) -> bool:
    return bool(_RE_EMAIL.match((email or "").strip()))


def _riga_prova() -> dict:
    """Dati fittizi di esempio per gli invii di prova."""
    oggi = date.today()
    m = oggi.month + 2
    fra_due_mesi = date(oggi.year + (m - 1) // 12, (m - 1) % 12 + 1, 1)
    return {"id": 0, "veicolo_id": 0, "cliente": "Mario Rossi", "email": "",
            "telefono": "", "targa": "AA123BB", "telaio": "", "marca": "FIAT",
            "modello": "PANDA", "scadenza": fra_due_mesi.isoformat()}


# ---------------------------------------------------------------------------
# Helper HTTP condivisi (libreria standard)
# ---------------------------------------------------------------------------

def _leggi_risposta(fp) -> dict:
    testo = fp.read().decode("utf-8", "replace")
    if not testo.strip():
        return {}
    try:
        return json.loads(testo)
    except ValueError:
        return {"raw": testo}


def _post_json(url: str, api_key: str, payload: dict, timeout: float = 15.0) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST", headers={
        "api-key": api_key, "content-type": "application/json", "accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, _leggi_risposta(r)
    except urllib.error.HTTPError as e:
        return e.code, _leggi_risposta(e)
    # urllib.error.URLError (rete assente/DNS/timeout) si propaga al chiamante.


def _get(url: str, api_key: str, timeout: float = 15.0) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers={"api-key": api_key, "accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, _leggi_risposta(r)
    except urllib.error.HTTPError as e:
        return e.code, _leggi_risposta(e)


# ---------------------------------------------------------------------------
# Coordinamento dei moduli opzionali
# ---------------------------------------------------------------------------

def _modulo(canale: str):
    """Il modulo che gestisce un canale, oppure None se non è installato."""
    try:
        if canale == "brevo":
            from . import modulo_email as m
        elif canale == "sms":
            from . import modulo_sms as m
        else:
            return None
        return m
    except ImportError:
        return None


def moduli_installati() -> dict[str, bool]:
    return {"brevo": _modulo("brevo") is not None, "sms": _modulo("sms") is not None}


def stato(cfg: dict) -> dict[str, bool]:
    """Per ogni canale: True se il modulo è installato E configurato."""
    risultato = {}
    for canale in ("brevo", "sms"):
        m = _modulo(canale)
        risultato[canale] = bool(m and m.configurato(cfg))
    return risultato


def invia(canale: str, righe: list[dict], cfg: dict, cartella_dati: Path) -> dict:
    m = _modulo(canale)
    if m is None:
        return {"inviati": 0, "inviati_ids": [], "errori": [f"modulo {canale} non installato"],
                "interrotto": True}
    return m.invia(righe, cfg, cartella_dati)


def prova(canale: str, cfg: dict, destinatario: str, cartella_dati: Path) -> dict:
    m = _modulo(canale)
    if m is None:
        return {"ok": False, "messaggio": f"Modulo {canale} non installato."}
    return m.prova(cfg, destinatario, cartella_dati)


def verifica_brevo(cfg: dict) -> dict:
    m = _modulo("brevo")
    if m is None:
        return {"ok": False, "messaggio": "Modulo email (Brevo) non installato."}
    return m.verifica(cfg)
