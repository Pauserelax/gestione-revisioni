"""Generatore dello storico clienti navigabile (pagina HTML autonoma).

Produce un unico file HTML con dentro tutti i dati: si apre nel browser,
si cerca per nome/telefono/targa/telaio e si naviga lo storico di ogni
cliente (veicoli negli anni, revisioni, contatti, scadenze).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from .scadenze import calcola_scadenze

MODELLO_PAGINA = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Storico clienti — Gestione Revisioni</title>
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; margin: 0;
         background: #f4f5f7; color: #1c1e21; }
  @media (prefers-color-scheme: dark) { body { background: #17191c; color: #e4e6eb; } }
  header { position: sticky; top: 0; background: #23395d; color: #fff;
           padding: 14px 20px; box-shadow: 0 1px 4px rgba(0,0,0,.25); z-index: 5; }
  header h1 { margin: 0 0 8px; font-size: 18px; }
  header .sub { font-size: 12px; opacity: .8; margin-bottom: 10px; }
  #cerca { width: 100%; max-width: 560px; padding: 10px 14px; font-size: 15px;
           border-radius: 8px; border: none; }
  main { max-width: 1000px; margin: 18px auto; padding: 0 16px; }
  .contatore { font-size: 13px; opacity: .7; margin-bottom: 10px; }
  .cliente { background: #fff; border-radius: 10px; padding: 14px 18px; margin-bottom: 12px;
             box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  @media (prefers-color-scheme: dark) { .cliente { background: #22252a; } }
  .cliente h2 { margin: 0; font-size: 16px; }
  .recapiti { font-size: 13px; opacity: .75; margin: 2px 0 8px; }
  .veicolo { border-left: 3px solid #23395d; padding: 6px 12px; margin: 8px 0; }
  .veicolo.dismesso { border-left-color: #999; opacity: .65; }
  .veicolo .titolo { font-weight: 600; font-size: 14px; }
  .badge { display: inline-block; font-size: 11px; font-weight: 600; border-radius: 10px;
           padding: 2px 8px; margin-left: 6px; vertical-align: middle; }
  .b-scaduta { background: #f4cccc; color: #7a1f1f; }
  .b-mese { background: #fff2cc; color: #7a5c00; }
  .b-futura { background: #d9ead3; color: #274e13; }
  .b-dismesso { background: #e0e0e0; color: #555; }
  .b-recupero { background: #f4cccc; color: #7a1f1f; }
  .evento { font-size: 12.5px; opacity: .85; margin-left: 4px; }
  .evento::before { content: "• "; opacity: .5; }
  .vuoto { text-align: center; padding: 40px; opacity: .6; }
</style>
</head>
<body>
<header>
  <h1>Storico clienti — Gestione Revisioni</h1>
  <div class="sub">generato il __DATA__ — __NCLIENTI__ clienti, __NVEICOLI__ veicoli</div>
  <input id="cerca" type="search" placeholder="Cerca per nome, telefono, targa o telaio…" autofocus>
</header>
<main>
  <div class="contatore" id="contatore"></div>
  <div id="lista"></div>
</main>
<script>
const CLIENTI = __DATI__;

function badgeScadenza(v) {
  if (!v.attivo) return '<span class="badge b-dismesso">dismesso</span>';
  if (!v.scadenza) return '';
  const oggi = new Date().toISOString().slice(0, 10);
  if (v.scadenza < oggi) return '<span class="badge b-scaduta">revisione SCADUTA ' + v.scadenza_it + '</span>';
  if (v.scadenza.slice(0, 7) === oggi.slice(0, 7)) return '<span class="badge b-mese">in scadenza ' + v.scadenza_it + '</span>';
  return '<span class="badge b-futura">prossima ' + v.scadenza_it + '</span>';
}

function cartaCliente(c) {
  let h = '<div class="cliente"><h2>' + c.nome +
          (c.da_recuperare ? ' <span class="badge b-recupero">DA RECUPERARE: senza veicolo attivo</span>' : '') +
          '</h2><div class="recapiti">' +
          (c.telefono ? '📞 ' + c.telefono + '  ' : '') + (c.email ? '✉️ ' + c.email : '') + '</div>';
  for (const v of c.veicoli) {
    h += '<div class="veicolo' + (v.attivo ? '' : ' dismesso') + '">' +
         '<div class="titolo">' + [v.marca, v.modello].filter(Boolean).join(' ') +
         (v.targa ? ' — ' + v.targa : '') + badgeScadenza(v) + '</div>' +
         '<div class="evento">telaio ' + (v.telaio || '-') + (v.imm ? ' — immatricolata ' + v.imm_it + ' (' + v.fonte + ')' : '') + '</div>';
    for (const e of v.eventi) h += '<div class="evento">' + e + '</div>';
    h += '</div>';
  }
  return h + '</div>';
}

function filtra() {
  const q = document.getElementById('cerca').value.trim().toLowerCase();
  const sel = q ? CLIENTI.filter(c => c.indice.includes(q)) : CLIENTI;
  document.getElementById('contatore').textContent =
    sel.length + ' clienti' + (q ? ' per "' + q + '"' : '');
  const mostra = sel.slice(0, 200);
  document.getElementById('lista').innerHTML =
    mostra.map(cartaCliente).join('') +
    (sel.length > 200 ? '<div class="vuoto">… altri ' + (sel.length - 200) + ' clienti: restringi la ricerca</div>' : '') +
    (sel.length === 0 ? '<div class="vuoto">Nessun cliente trovato</div>' : '');
}
document.getElementById('cerca').addEventListener('input', filtra);
filtra();
</script>
</body>
</html>
"""


def _it(iso: str | None) -> str:
    if not iso:
        return ""
    a, m, g = iso[:10].split("-")
    return f"{g}/{m}/{a}"


def genera_storico(conn: sqlite3.Connection, percorso: Path) -> Path:
    scadenze = {s.veicolo_id: s for s in calcola_scadenze(conn, includi_esclusi=True)}

    clienti = []
    n_veicoli = 0
    for c in conn.execute("SELECT * FROM clienti ORDER BY nome"):
        veicoli = []
        ha_attivi = False
        for v in conn.execute(
            "SELECT * FROM veicoli WHERE cliente_id = ? ORDER BY IFNULL(data_immatricolazione,'') DESC", (c["id"],)
        ):
            n_veicoli += 1
            if v["attivo"]:
                ha_attivi = True
            s = scadenze.get(v["id"])
            eventi = []
            for r in conn.execute(
                "SELECT data_revisione, fonte FROM revisioni_effettuate WHERE veicolo_id = ? ORDER BY data_revisione DESC", (v["id"],)
            ):
                eventi.append(f"revisione effettuata il {_it(r['data_revisione'])} ({r['fonte']})")
            for k in conn.execute(
                "SELECT data_contatto, esito, note FROM contatti WHERE veicolo_id = ? ORDER BY data_contatto DESC LIMIT 8", (v["id"],)
            ):
                nota = f" — {k['note']}" if k["note"] else ""
                eventi.append(f"{_it(k['data_contatto'])}: {k['esito'].replace('_', ' ')}{nota}")
            veicoli.append({
                "marca": v["marca"] or "", "modello": v["modello"] or "",
                "targa": v["targa"] or "", "telaio": v["telaio"] or "",
                "imm": v["data_immatricolazione"] or "", "imm_it": _it(v["data_immatricolazione"]),
                "fonte": "presunta" if v["fonte_data"] == "mese_report" else (v["fonte_data"] or ""),
                "attivo": bool(v["attivo"]),
                "scadenza": s.scadenza.isoformat() if s and s.scadenza and v["attivo"] else "",
                "scadenza_it": s.scadenza.strftime("%d/%m/%Y") if s and s.scadenza and v["attivo"] else "",
                "eventi": eventi,
            })
        if not veicoli:
            continue
        indice = " ".join(filter(None, [c["nome"], c["telefono"] or "", c["email"] or ""] +
                                 [v["targa"] + " " + v["telaio"] for v in veicoli])).lower()
        clienti.append({
            "nome": c["nome"], "telefono": c["telefono"] or "", "email": c["email"] or "",
            "da_recuperare": not ha_attivi, "veicoli": veicoli, "indice": indice,
        })

    html = (MODELLO_PAGINA
            .replace("__DATA__", date.today().strftime("%d/%m/%Y"))
            .replace("__NCLIENTI__", str(len(clienti)))
            .replace("__NVEICOLI__", str(n_veicoli))
            .replace("__DATI__", json.dumps(clienti, ensure_ascii=False)))
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(html, encoding="utf-8")
    return percorso
