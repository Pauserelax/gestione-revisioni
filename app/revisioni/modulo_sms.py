"""Modulo opzionale: invio SMS automatico via gateway HTTP.

Modulo opzionale di "Gestione Revisioni". Se questo file non è presente,
il canale SMS resta non disponibile e la dashboard offre solo l'export Excel
per il caricamento manuale (SMS Cafè).

Il gateway è generico e parametrico (qualsiasi servizio con una chiamata HTTP
GET/POST, tipo "SMS Script" di SMSBiz): URL, metodo, nomi dei parametri e
credenziali si impostano in dati/config_invii.txt. Il testo è quello di
dati/sms_testo.txt, con lo stesso limite di 160 caratteri dell'export.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from . import invii

DISPONIBILE = True
CHIAVI_MINIME = ("sms_url", "sms_utente", "sms_password",
                 "sms_param_utente", "sms_param_password", "sms_param_numero", "sms_param_testo")


def configurato(cfg: dict) -> bool:
    return all(cfg.get(k) for k in CHIAVI_MINIME)


def _chiama_gateway(cfg: dict, numero: str, testo: str, timeout: float = 15.0) -> tuple[bool, str]:
    """Una chiamata al gateway configurato. Ritorna (ok, risposta_troncata)."""
    campi = {
        cfg["sms_param_utente"]: cfg["sms_utente"],
        cfg["sms_param_password"]: cfg["sms_password"],
        cfg["sms_param_numero"]: numero,
        cfg["sms_param_testo"]: testo,
    }
    if cfg.get("sms_param_mittente") and cfg.get("sms_mittente"):
        campi[cfg["sms_param_mittente"]] = cfg["sms_mittente"]
    corpo = urllib.parse.urlencode(campi, encoding="utf-8")
    metodo = (cfg.get("sms_metodo") or "GET").upper()
    if metodo == "POST":
        req = urllib.request.Request(cfg["sms_url"], data=corpo.encode("utf-8"), method="POST",
                                      headers={"content-type": "application/x-www-form-urlencoded"})
    else:
        separatore = "&" if "?" in cfg["sms_url"] else "?"
        req = urllib.request.Request(cfg["sms_url"] + separatore + corpo, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            risposta = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: " + e.read().decode("utf-8", "replace")[:200]
    atteso = (cfg.get("sms_ok_contiene") or "").strip()
    ok = (atteso.lower() in risposta.lower()) if atteso else True
    return ok, risposta.strip()[:200]


def _componi_messaggio(r: dict, testo_template: str) -> str:
    from .scadenze import ScadenzaVeicolo
    from .sms import _componi
    finta = ScadenzaVeicolo(
        veicolo_id=r.get("veicolo_id") or 0, telaio=r.get("telaio") or "",
        marca=r.get("marca") or "", modello=r.get("modello") or "",
        punto_vendita="", cliente=r.get("cliente") or "", telefono=r.get("telefono") or "",
        data_immatricolazione=None, fonte_data="", ultima_revisione=None,
        scadenza=date.fromisoformat(r["scadenza"]) if r.get("scadenza") else None,
        giorni_rimanenti=None, stato="", ultimo_esito="", targa=r.get("targa") or "")
    return _componi(testo_template, finta)


def invia(righe: list[dict], cfg: dict, cartella_dati: Path) -> dict:
    """Invia via gateway il testo SMS a ogni riga di coda con cellulare valido,
    riusando la composizione (template, limite 160) dell'export smscafè.

    `righe` è l'output di database.coda_invio(conn, 'sms', solo_in_coda=True)
    convertito in dict."""
    from .sms import TESTO_PREDEFINITO, _cellulare, _testo_template, controlla_template

    testo = _testo_template(cartella_dati / "sms_testo.txt", TESTO_PREDEFINITO)
    esito = {"inviati": 0, "inviati_ids": [], "saltati_senza_numero": 0,
              "errori": [], "interrotto": False}
    try:
        controlla_template(testo)
    except ValueError as e:
        esito["errori"].append(str(e))
        esito["interrotto"] = True
        return esito

    pausa = float(cfg.get("sms_pausa_ms") or 0) / 1000
    for r in righe:
        numero = _cellulare(r.get("telefono") or "")
        if not numero:
            esito["saltati_senza_numero"] += 1
            continue
        messaggio = _componi_messaggio({**r, "telefono": numero}, testo)
        try:
            ok, risposta = _chiama_gateway(cfg, numero, messaggio)
        except urllib.error.URLError as e:
            esito["errori"].append(f"rete assente: {e.reason} — invio interrotto")
            esito["interrotto"] = True
            break
        if ok:
            esito["inviati"] += 1
            esito["inviati_ids"].append(r["id"])
        else:
            esito["errori"].append(f"{r.get('cliente', '?')} ({numero}): {risposta}")
        if pausa:
            time.sleep(pausa)
    return esito


def prova(cfg: dict, numero: str, cartella_dati: Path) -> dict:
    """Invia un solo SMS di prova (testo del template + dati fittizi) al numero dato."""
    from .sms import TESTO_PREDEFINITO, _cellulare, _testo_template, controlla_template

    cell = _cellulare(numero)
    if not cell:
        return {"ok": False, "messaggio": f"Numero non valido come cellulare: {numero}"}
    testo = _testo_template(cartella_dati / "sms_testo.txt", TESTO_PREDEFINITO)
    try:
        controlla_template(testo)
    except ValueError as e:
        return {"ok": False, "messaggio": str(e)}
    messaggio = _componi_messaggio({**invii._riga_prova(), "telefono": cell}, testo)
    try:
        ok, risposta = _chiama_gateway(cfg, cell, messaggio)
    except urllib.error.URLError as e:
        return {"ok": False, "messaggio": f"Rete non raggiungibile: {e.reason}"}
    if ok:
        return {"ok": True, "messaggio": f"SMS di prova inviato a {cell}. Risposta gateway: {risposta}"}
    return {"ok": False, "messaggio": f"Il gateway non ha confermato l'invio. Risposta: {risposta}"}
