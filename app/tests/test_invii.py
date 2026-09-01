"""Test dei moduli di invio (email Brevo, SMS gateway) e del coordinatore.

Esecuzione:  python3 app/tests/test_invii.py
Non richiede rete: le chiamate HTTP sono sostituite da fake.
"""
import sys, json, io, tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import revisioni.invii as invii
import revisioni.modulo_email as me
import revisioni.modulo_sms as ms

errori = []
def check(cond, msg):
    print(("ok: " if cond else "FAIL: ") + msg)
    if not cond:
        errori.append(msg)

# --- leggi_config (coordinatore) ---
with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp) / "config_invii.txt"
    cfg = invii.leggi_config(p)
    check(p.exists(), "leggi_config crea il file col template")
    check(cfg.get("sms_metodo") == "GET", "default sms_metodo=GET")
    check(invii.stato(cfg) == {"brevo": False, "sms": False}, f"stato col template vuoto: {invii.stato(cfg)}")

    p2 = Path(tmp) / "c2.txt"
    p2.write_text(
        "brevo_api_key = xkeysib-abc  # commento\n"
        "brevo_mittente_email=\"info@x.it\"\n"
        "brevo_template_id = 12\n"
        "sms_url = http://gw/send\n", encoding="utf-8")
    cfg2 = invii.leggi_config(p2)
    check(cfg2["brevo_api_key"] == "xkeysib-abc", "commento inline rimosso")
    check(cfg2["brevo_mittente_email"] == "info@x.it", "virgolette rimosse")
    check(me.configurato(cfg2) and not ms.configurato(cfg2), "modulo_email configurato, modulo_sms no")
    check(invii.stato(cfg2) == {"brevo": True, "sms": False}, f"stato: {invii.stato(cfg2)}")

# --- _valida_email ---
check(invii._valida_email("a@b.it") and not invii._valida_email("a@b")
      and not invii._valida_email("") and not invii._valida_email("a b@c.it"), "validazione email")

# --- modulo_email.invia con urlopen monkeypatchato (su invii, che ospita _post_json) ---
class FakeResp:
    def __init__(self, status, body):
        self.status = status
        self._body = json.dumps(body).encode()
    def read(self): return self._body
    def __enter__(self): return self
    def __exit__(self, *a): return False

cfg_brevo = {"brevo_api_key": "k", "brevo_mittente_email": "m@x.it",
             "brevo_mittente_nome": "Test", "brevo_template_id": "5"}
righe = [
    {"id": 1, "email": "a@x.it", "cliente": "mario rossi", "targa": "AA111AA",
     "marca": "FIAT", "modello": "PANDA", "scadenza": "2026-11-30"},
    {"id": 2, "email": "", "cliente": "no email"},
    {"id": 3, "email": "c@x.it", "cliente": "carlo verdi", "targa": "BB222BB",
     "marca": "FORD", "modello": "FOCUS", "scadenza": "2026-10-15"},
]
with mock.patch.object(invii.urllib.request, "urlopen", return_value=FakeResp(201, {"messageId": "1"})):
    esito = invii.invia("brevo", righe, cfg_brevo, Path("."))
check(esito["inviati"] == 2 and esito["saltati_senza_email"] == 1 and sorted(esito["inviati_ids"]) == [1, 3],
      f"invia brevo: {esito}")

with mock.patch.object(invii.urllib.request, "urlopen",
                        side_effect=[FakeResp(201, {}), FakeResp(429, {"message": "quota"})]):
    esito2 = me.invia(righe[:1] + [{"id": 9, "email": "z@x.it", "cliente": "z"}], cfg_brevo, chunk=1)
check(esito2["interrotto"] and esito2["inviati_ids"] == [1], f"429 interrompe, solo 1° blocco: {esito2}")

import urllib.error
with mock.patch.object(invii.urllib.request, "urlopen", side_effect=urllib.error.URLError("no net")):
    esito3 = invii.invia("brevo", righe[:1], cfg_brevo, Path("."))
check(esito3["interrotto"] and esito3["inviati_ids"] == [], f"URLError: {esito3}")

# --- verifica_brevo via coordinatore ---
with mock.patch.object(invii.urllib.request, "urlopen", return_value=FakeResp(200, {"email": "acc@x.it"})):
    v = invii.verifica_brevo(cfg_brevo)
check(v["ok"] and "acc@x.it" in v["messaggio"], f"verifica_brevo ok: {v}")

# --- modulo_sms.invia con gateway finto (patch su modulo_sms.urllib.request) ---
with tempfile.TemporaryDirectory() as tmp:
    cartella = Path(tmp)
    (cartella / "sms_testo.txt").write_text(
        "Gentile {NOME}, la revisione della sua {MODELLO} targa {TARGA} scade entro {MESE}. "
        "Prenoti: 02 0000000", encoding="utf-8")
    cfg_sms = {"sms_url": "http://gw/send", "sms_metodo": "GET",
               "sms_param_utente": "user", "sms_param_password": "pass",
               "sms_param_numero": "numero", "sms_param_testo": "testo",
               "sms_utente": "u", "sms_password": "p", "sms_ok_contiene": "OK"}
    righe_sms = [
        {"id": 10, "veicolo_id": 1, "telefono": "3357911234", "cliente": "mario rossi",
         "targa": "AA111AA", "marca": "FIAT", "modello": "PANDA", "scadenza": "2026-11-30", "telaio": ""},
        {"id": 11, "veicolo_id": 2, "telefono": "0299887766", "cliente": "telefono fisso",
         "targa": "", "marca": "", "modello": "", "scadenza": "", "telaio": ""},
    ]
    with mock.patch.object(ms.urllib.request, "urlopen") as m:
        m.return_value.__enter__.return_value.read.return_value = b"OK 123"
        esito_sms = invii.invia("sms", righe_sms, cfg_sms, cartella)
    check(esito_sms["inviati"] == 1 and esito_sms["saltati_senza_numero"] == 1
          and esito_sms["inviati_ids"] == [10], f"invia sms: {esito_sms}")

    with mock.patch.object(ms.urllib.request, "urlopen") as m:
        m.return_value.__enter__.return_value.read.return_value = b"ERRORE credito esaurito"
        esito_sms2 = invii.invia("sms", righe_sms[:1], cfg_sms, cartella)
    check(esito_sms2["inviati"] == 0 and len(esito_sms2["errori"]) == 1, f"risposta senza OK: {esito_sms2}")

    (cartella / "sms_testo.txt").write_text("Gentile {NOME}, chiami {TEL_OFFICINA}", encoding="utf-8")
    esito_sms3 = invii.invia("sms", righe_sms, cfg_sms, cartella)
    check(esito_sms3["interrotto"] and esito_sms3["inviati"] == 0, f"template incompleto blocca: {esito_sms3}")

# --- prova (coordinatore) ---
with tempfile.TemporaryDirectory() as tmp:
    cartella = Path(tmp)
    (cartella / "sms_testo.txt").write_text(
        "Gentile {NOME}, revisione {TARGA} entro {MESE}. 02 0000000", encoding="utf-8")
    with mock.patch.object(invii.urllib.request, "urlopen", return_value=FakeResp(201, {})):
        pv = invii.prova("brevo", cfg_brevo, "prova@x.it", cartella)
    check(pv["ok"], f"prova brevo: {pv}")
    pv2 = invii.prova("brevo", cfg_brevo, "non-email", cartella)
    check(not pv2["ok"], f"prova brevo email non valida: {pv2}")
    with mock.patch.object(ms.urllib.request, "urlopen") as m:
        m.return_value.__enter__.return_value.read.return_value = b"OK"
        pv3 = invii.prova("sms", cfg_sms, "3357911234", cartella)
    check(pv3["ok"], f"prova sms: {pv3}")

# --- degradazione: canale non installato ---
_orig = invii._modulo
invii._modulo = lambda c: None
try:
    check(invii.stato({}) == {"brevo": False, "sms": False}, "moduli assenti -> stato tutto False")
    e = invii.invia("brevo", [], {}, Path("."))
    check(e["interrotto"] and "non installato" in e["errori"][0], f"invia con modulo assente: {e}")
    check(not invii.verifica_brevo({})["ok"], "verifica_brevo con modulo assente")
finally:
    invii._modulo = _orig

print()
print(f"{len(errori)} FALLIMENTI" if errori else "Tutti i test OK")
sys.exit(1 if errori else 0)
