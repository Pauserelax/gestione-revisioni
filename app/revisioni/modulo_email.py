"""Modulo opzionale: invio email automatico via API Brevo.

Componente aggiuntivo di "Gestione Revisioni". Se questo file non è presente,
il canale email resta non disponibile e la dashboard offre solo l'export CSV
per il caricamento manuale su Brevo.

La DEM si disegna come *template* in Brevo; qui si invia in transazionale
(POST /v3/smtp/email, batch `messageVersions`) passando i dati del veicolo
come `params` — nel template si usano {{params.NOME}}, {{params.TARGA}}, ecc.
"""

from __future__ import annotations

import urllib.error
from datetime import date
from pathlib import Path

from . import invii
from .sms import MESI_IT

DISPONIBILE = True
CHIAVI_MINIME = ("brevo_api_key", "brevo_mittente_email", "brevo_template_id")


def configurato(cfg: dict) -> bool:
    return all(cfg.get(k) for k in CHIAVI_MINIME)


def _params(r: dict) -> dict:
    d = date.fromisoformat(r["scadenza"]) if r.get("scadenza") else None
    return {
        "NOME": (r.get("cliente") or "").title(),
        "TARGA": r.get("targa") or "",
        "MARCA": r.get("marca") or "",
        "MODELLO": r.get("modello") or "",
        "SCADENZA": d.strftime("%d/%m/%Y") if d else "",
        "MESE": f"{MESI_IT[d.month]} {d.year}" if d else "",
    }


def _sender(cfg: dict) -> dict:
    return {"email": cfg["brevo_mittente_email"],
            "name": cfg.get("brevo_mittente_nome") or cfg["brevo_mittente_email"]}


def verifica(cfg: dict) -> dict:
    """Controlla che la chiave API sia valida (GET /v3/account)."""
    if not cfg.get("brevo_api_key"):
        return {"ok": False, "messaggio": "Chiave API Brevo non impostata in dati/config_invii.txt."}
    try:
        stato, dati = invii._get(f"{invii._BASE_BREVO}/v3/account", cfg["brevo_api_key"])
    except urllib.error.URLError as e:
        return {"ok": False, "messaggio": f"Rete non raggiungibile: {e.reason}"}
    if stato == 200:
        return {"ok": True, "messaggio": f"Connessione OK — account Brevo: {dati.get('email', '?')}."}
    if stato == 401:
        return {"ok": False, "messaggio": "Chiave API Brevo rifiutata (401): controllala in dati/config_invii.txt."}
    return {"ok": False, "messaggio": f"Risposta inattesa da Brevo (HTTP {stato})."}


def invia(righe: list[dict], cfg: dict, cartella_dati: Path | None = None, chunk: int = 100) -> dict:
    """Invia il template Brevo a ogni riga di coda con email valida.

    `righe` è l'output di database.coda_invio(conn, 'brevo', solo_in_coda=True)
    convertito in dict. Chiamata batch (messageVersions) ogni `chunk` destinatari:
    se un blocco fallisce, i successivi vengono comunque tentati (l'operatore
    vede l'errore e riprova solo quel blocco, che resta in coda)."""
    validi, saltati = [], 0
    for r in righe:
        if invii._valida_email(r.get("email")):
            validi.append(r)
        else:
            saltati += 1

    esito = {"inviati": 0, "inviati_ids": [], "saltati_senza_email": saltati,
              "errori": [], "interrotto": False}
    if not validi:
        return esito

    sender = _sender(cfg)
    for i in range(0, len(validi), chunk):
        blocco = validi[i:i + chunk]
        payload = {
            "sender": sender,
            "templateId": int(cfg["brevo_template_id"]),
            "messageVersions": [
                {"to": [{"email": r["email"].strip(), "name": (r.get("cliente") or "").title()}],
                 "params": _params(r)}
                for r in blocco
            ],
        }
        if cfg.get("brevo_reply_to"):
            payload["replyTo"] = {"email": cfg["brevo_reply_to"]}
        try:
            stato, risposta = invii._post_json(
                f"{invii._BASE_BREVO}/v3/smtp/email", cfg["brevo_api_key"], payload)
        except urllib.error.URLError as e:
            esito["errori"].append(f"rete assente: {e.reason} — invio interrotto")
            esito["interrotto"] = True
            break
        if stato in (200, 201, 202):
            esito["inviati"] += len(blocco)
            esito["inviati_ids"].extend(r["id"] for r in blocco)
        elif stato == 429:
            esito["errori"].append(
                f"limite Brevo raggiunto (429): {len(validi) - i} email non inviate, riprovare più tardi.")
            esito["interrotto"] = True
            break
        else:
            messaggio = risposta.get("message") or risposta.get("raw") or str(risposta)
            esito["errori"].append(
                f"Brevo {stato}: {str(messaggio)[:200]} (blocco di {len(blocco)} non inviato)")
    return esito


def prova(cfg: dict, email: str, cartella_dati: Path | None = None) -> dict:
    """Invia una sola email di prova (template + dati fittizi) all'indirizzo dato."""
    if not invii._valida_email(email):
        return {"ok": False, "messaggio": f"Indirizzo email non valido: {email}"}
    payload = {
        "sender": _sender(cfg),
        "templateId": int(cfg["brevo_template_id"]),
        "to": [{"email": email.strip(), "name": "Prova"}],
        "params": _params(invii._riga_prova()),
    }
    if cfg.get("brevo_reply_to"):
        payload["replyTo"] = {"email": cfg["brevo_reply_to"]}
    try:
        stato, risposta = invii._post_json(
            f"{invii._BASE_BREVO}/v3/smtp/email", cfg["brevo_api_key"], payload)
    except urllib.error.URLError as e:
        return {"ok": False, "messaggio": f"Rete non raggiungibile: {e.reason}"}
    if stato in (200, 201, 202):
        return {"ok": True, "messaggio": f"Email di prova inviata a {email}. Controlla la casella (anche lo spam)."}
    messaggio = risposta.get("message") or risposta.get("raw") or str(risposta)
    return {"ok": False, "messaggio": f"Brevo ha rifiutato (HTTP {stato}): {str(messaggio)[:200]}"}
