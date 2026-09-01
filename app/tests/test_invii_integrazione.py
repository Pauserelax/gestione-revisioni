"""Test end-to-end: dashboard + mock Brevo + mock gateway SMS.

Esecuzione:  python3 app/tests/test_invii_integrazione.py
Avvia server finti in locale; non esce traffico reale.
"""
import json, os, sys, threading, time, urllib.request, urllib.error, tempfile, shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

tmp = tempfile.mkdtemp()
dbfile = Path(tmp) / "dati" / "revisioni.db"
dbfile.parent.mkdir(parents=True)

# --- mock Brevo + mock gateway SMS ---
brevo_calls, sms_calls = [], []

class Mock(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body):
        b = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)
    def do_GET(self):
        if self.path.startswith("/sms"):
            sms_calls.append(self.path)
            self.send_response(200); self.send_header("Content-Length", "5"); self.end_headers()
            self.wfile.write(b"OK ok")
            return
        if self.path == "/v3/account":
            return self._send(200, {"email": "mock@brevo"})
        self._send(404, {})
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/v3/smtp/email":
            brevo_calls.append(payload)
            return self._send(201, {"messageId": "x"})
        self._send(404, {})

mock = ThreadingHTTPServer(("127.0.0.1", 0), Mock)
mock_port = mock.server_address[1]
threading.Thread(target=mock.serve_forever, daemon=True).start()

os.environ["REVISIONI_BREVO_BASE"] = f"http://127.0.0.1:{mock_port}"

from revisioni import db as database, demo
from revisioni.web import crea_handler
from http.server import ThreadingHTTPServer as THS

conn = database.apri_db(dbfile)
demo.carica(conn)
# metti 3 veicoli in coda brevo e 3 in coda sms; forza email/telefono
vids = [r["id"] for r in conn.execute("SELECT id FROM veicoli LIMIT 4")]
conn.execute("UPDATE clienti SET email='cliente@example.com' WHERE id IN (SELECT cliente_id FROM veicoli WHERE id IN (%s))" % ",".join(map(str, vids[:3])))
conn.execute("UPDATE clienti SET telefono='3357911234' WHERE id IN (SELECT cliente_id FROM veicoli WHERE id IN (%s))" % ",".join(map(str, vids[:3])))
conn.commit()
database.aggiungi_a_coda(conn, vids[:3], "brevo", {v: "2026-11-30" for v in vids[:3]})
database.aggiungi_a_coda(conn, vids[:3], "sms", {v: "2026-11-30" for v in vids[:3]})
# sms_testo.txt valido (senza {TEL_OFFICINA})
(dbfile.parent / "sms_testo.txt").write_text(
    "Gentile {NOME}, la revisione della sua {MODELLO} targa {TARGA} scade entro {MESE}. Prenoti: 02 0000000",
    encoding="utf-8")
conn.close()

srv = THS(("127.0.0.1", 0), crea_handler(dbfile))
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{port}"

def call(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req) as r:
        return r.status, json.loads(r.read())

errori = []
def check(c, m):
    print(("ok: " if c else "FAIL: ") + m)
    if not c: errori.append(m)

# 1) config non compilata
st, r = call("/api/invii-config")
check(r == {"brevo": False, "sms": False}, f"config vuota: {r}")
check((dbfile.parent / "config_invii.txt").exists(), "config_invii.txt creato")

# 2) invio con config non valida -> 400
try:
    call("/api/coda-invia", {"canale": "brevo"})
    check(False, "atteso 400 con brevo non configurato")
except urllib.error.HTTPError as e:
    check(e.code == 400, f"coda-invia brevo non configurato -> {e.code}")

# 3) compila config e ricarica
(dbfile.parent / "config_invii.txt").write_text(
    "brevo_api_key = k\nbrevo_mittente_email = m@x.it\nbrevo_template_id = 7\n"
    "sms_url = http://127.0.0.1:%d/sms\nsms_metodo = GET\n"
    "sms_param_utente = u\nsms_param_password = p\nsms_param_numero = n\nsms_param_testo = t\n"
    "sms_utente = xx\nsms_password = yy\nsms_ok_contiene = OK\n" % mock_port,
    encoding="utf-8")
st, r = call("/api/invii-config")
check(r == {"brevo": True, "sms": True}, f"config completa: {r}")

# 4) invio coda brevo
st, r = call("/api/coda-invia", {"canale": "brevo"})
check(r.get("inviati") == 3 and r.get("salvati") == 3, f"brevo inviati/salvati: {r}")
check(len(brevo_calls) == 1, f"1 chiamata batch a Brevo: {len(brevo_calls)}")
check(len(brevo_calls[0]["messageVersions"]) == 3, "3 messageVersions")
mv = brevo_calls[0]["messageVersions"][0]
check("NOME" in mv["params"] and "SCADENZA" in mv["params"], f"params: {mv['params']}")

# 5) ri-invio: coda ora vuota
st, r = call("/api/coda-invia", {"canale": "brevo"})
check(r.get("inviati") == 0, f"seconda volta coda vuota: {r}")

# 6) invio coda sms
st, r = call("/api/coda-invia", {"canale": "sms"})
check(r.get("inviati") == 3 and r.get("salvati") == 3, f"sms inviati/salvati: {r}")
check(len(sms_calls) == 3, f"3 chiamate al gateway SMS: {len(sms_calls)}")

# 7) prova email
st, r = call("/api/invii-prova", {"canale": "brevo", "destinatario": "prova@example.com"})
check(r.get("ok") is True, f"prova brevo: {r}")
check(len(brevo_calls) == 2 and "to" in brevo_calls[1], "prova brevo = chiamata singola con 'to'")

# 8) prova sms
st, r = call("/api/invii-prova", {"canale": "sms", "destinatario": "3357911234"})
check(r.get("ok") is True, f"prova sms: {r}")

# 9) prova email non valida
st, r = call("/api/invii-prova", {"canale": "brevo", "destinatario": "non-una-email"})
check(r.get("ok") is False, f"prova brevo email non valida: {r}")

# 10) verifica brevo
st, r = call("/api/invii-verifica-brevo", {})
check(r.get("ok") is True and "mock@brevo" in r["messaggio"], f"verifica brevo: {r}")

# 11) DB: inviato_il valorizzato e contatti registrati
conn = database.apri_db(dbfile)
n_inviati = conn.execute("SELECT COUNT(*) c FROM code_invio WHERE inviato_il IS NOT NULL").fetchone()["c"]
n_cont = conn.execute("SELECT COUNT(*) c FROM contatti WHERE esito IN ('email_inviata','sms_inviato') AND note LIKE 'invio automatico%'").fetchone()["c"]
check(n_inviati == 6, f"6 righe coda marcate inviate: {n_inviati}")
check(n_cont == 6, f"6 contatti 'invio automatico': {n_cont}")
conn.close()

# 12) regressione: /api/riepilogo risponde
st, r = call("/api/riepilogo")
check(st == 200 and "sms" in r, "riepilogo ok")

shutil.rmtree(tmp, ignore_errors=True)
print()
print(f"{len(errori)} FALLIMENTI" if errori else "Tutti i test di integrazione OK")
sys.exit(1 if errori else 0)
