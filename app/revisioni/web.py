"""Dashboard web locale per la gestione operativa dello scadenzario.

Server HTTP in sola libreria standard: gira in locale, nessun dato esce dal
computer. Avvio: python3 -m revisioni web
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import db as database
from .scadenze import calcola_scadenze, da_contattare

_lock = threading.Lock()

PAGINA = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gestione Revisioni</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; margin: 0; background: #f2f3f5; color: #1c1e21; }
  header { background: #23395d; color: #fff; padding: 12px 20px; display: flex; align-items: center; gap: 18px; flex-wrap: wrap; }
  header h1 { font-size: 17px; margin: 0; }
  .chip { background: rgba(255,255,255,.14); border-radius: 14px; padding: 4px 12px; font-size: 13px; }
  .chip b { font-size: 15px; }
  nav { background: #fff; padding: 0 20px; border-bottom: 1px solid #ddd; display: flex; gap: 4px; }
  nav button { border: none; background: none; padding: 12px 16px; font-size: 14px; cursor: pointer; border-bottom: 3px solid transparent; }
  nav button.attivo { border-bottom-color: #23395d; font-weight: 600; }
  main { padding: 16px 20px; max-width: 1400px; margin: 0 auto; }
  .filtri { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; align-items: center; }
  .filtri button { border: 1px solid #ccc; background: #fff; border-radius: 14px; padding: 5px 12px; cursor: pointer; font-size: 13px; }
  .filtri button.attivo { background: #23395d; color: #fff; border-color: #23395d; }
  input[type=search] { padding: 8px 12px; border: 1px solid #ccc; border-radius: 8px; font-size: 14px; min-width: 260px; }
  table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  th, td { padding: 8px 10px; text-align: left; font-size: 13px; border-bottom: 1px solid #eee; vertical-align: top; }
  th { background: #fafbfc; font-size: 12px; text-transform: uppercase; letter-spacing: .03em; color: #555; }
  tr.SCADUTA td:first-child { border-left: 4px solid #cc4125; }
  tr.IN_SCADENZA td:first-child { border-left: 4px solid #e8b400; }
  tr.PROSSIMA td:first-child { border-left: 4px solid #6aa84f; }
  tr.DATI_MANCANTI td:first-child { border-left: 4px solid #9aa4b2; }
  .stato { font-weight: 700; font-size: 11px; }
  .SCADUTA .stato { color: #cc4125; } .IN_SCADENZA .stato { color: #9c7b00; } .PROSSIMA .stato { color: #38761d; }
  .DATI_MANCANTI .stato { color: #5b6673; }
  .azioni { display: flex; gap: 4px; flex-wrap: wrap; }
  .azioni button { border: 1px solid #ccc; background: #fff; border-radius: 6px; padding: 3px 8px; font-size: 12px; cursor: pointer; }
  .azioni button:hover { background: #eef2f8; }
  .badge { display: inline-block; font-size: 11px; border-radius: 10px; padding: 1px 8px; margin-top: 2px; }
  .b-lead { background: #d0e0f0; color: #1c4587; }
  .b-avviso { background: #fce5cd; color: #b45309; }
  .b-esito { background: #e0e0e0; color: #444; }
  .b-tel { background: #f4cccc; color: #7a1f1f; }
  .btn-tel { border: none; background: none; cursor: pointer; font-size: 13px; padding: 0 2px; opacity: .55; }
  .btn-tel:hover { opacity: 1; }
  .cliente-card { background: #fff; border-radius: 8px; padding: 12px 16px; margin-bottom: 10px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  .muted { color: #777; font-size: 12px; }
  #note-conteggio { color: #555; font-size: 13px; margin: 8px 0; }
  .kpi-griglia { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }
  .kpi { background: #fff; border-radius: 8px; padding: 12px 18px; box-shadow: 0 1px 3px rgba(0,0,0,.08); min-width: 150px; }
  .kpi b { display: block; font-size: 26px; margin-top: 2px; }
  .kpi .muted { font-size: 12px; }
  .grafico-card { background: #fff; border-radius: 8px; padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,.08); margin-bottom: 16px; }
  .grafico-card h3 { margin: 0 0 2px; font-size: 15px; }
  .grafico { display: flex; align-items: flex-end; gap: 2px; height: 150px; margin-top: 14px; }
  .colonna { flex: 1; min-width: 3px; display: flex; flex-direction: column; justify-content: flex-end; gap: 2px; height: 100%; cursor: default; }
  .colonna div:first-child { border-radius: 4px 4px 0 0; }
  .seg-nostri { background: #2a78d6; }
  .seg-esterni { background: #eb6834; }
  .colonna:hover div { filter: brightness(1.15); }
  .mesi { display: flex; gap: 2px; margin-top: 4px; }
  .mesi span { flex: 1; min-width: 3px; font-size: 10px; color: #777; text-align: left; overflow: visible; white-space: nowrap; }
  .legenda { display: flex; gap: 16px; font-size: 12px; color: #555; margin-top: 10px; }
  .legenda i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 5px; vertical-align: -1px; }
</style>
</head>
<body>
<header>
  <h1>🔧 Gestione Revisioni</h1>
  <span class="chip">⏰ Scadono questo mese <b id="k-mese">–</b></span>
  <span class="chip">📞 Chiamate (+1 mese) <b id="k-chiamate">–</b></span>
  <span class="chip">✉️ SMS da inviare (+2 mesi) <b id="k-sms">–</b></span>
  <span class="chip">🧊 Cold (mai contattati) <b id="k-cold">–</b></span>
  <span class="chip">📇 Dati mancanti <b id="k-dati">–</b></span>
  <span class="chip">🔄 Da recuperare <b id="k-recupero">–</b></span>
  <span class="chip">🎯 Lead Tcar <b id="k-lead">–</b></span>
  <span style="margin-left:auto">
    <button id="btn-aggiorna" style="border:none;border-radius:8px;padding:8px 14px;cursor:pointer;background:#e8b400;color:#1c1e21;font-weight:600" onclick="document.getElementById('file-aggiorna').click()">⬆️ Aggiorna dati</button>
    <input type="file" id="file-aggiorna" multiple accept=".xlsx,.xls,.pdf" style="display:none">
  </span>
</header>
<nav>
  <button data-tab="chiamate" class="attivo">📞 Da chiamare</button>
  <button data-tab="recupero">🔄 Da recuperare</button>
  <button data-tab="cerca">🔍 Cerca cliente</button>
  <button data-tab="invii">📤 Invii</button>
  <button data-tab="stat">📊 Statistiche</button>
  <button data-tab="filtri">⚙️ Filtri</button>
</nav>
<main>
  <section id="tab-chiamate">
    <div class="filtri">
      <button data-f="MESE_CORRENTE" class="attivo">⏰ Scadono questo mese</button>
      <button data-f="CHIAMATA">📞 Da chiamare (+1 mese)</button>
      <button data-f="SMS">✉️ SMS (+2 mesi)</button>
      <button data-f="COLD">🧊 Cold (mai contattati)</button>
      <button data-f="RISCALDA">♻️ Riscalda clienti</button>
      <button data-f="DATI">📇 Dati mancanti</button>
      <button data-f="LEAD">🎯 Con lead Tcar</button>
      <label style="font-size:13px">📅 Vai al mese: <input type="month" id="mese-futuro"></label>
      <input type="search" id="cerca-chiamate" placeholder="Filtra per nome, targa, telaio…">
      <span id="strumenti-sms" style="display:none">
        <button onclick="scaricaSms(false)">⬇️ Scarica lista SMS (smscafè)</button>
        <button onclick="segnaSms(false)">✔️ Segna tutti come inviati</button>
      </span>
      <span id="strumenti-arretrato" style="display:none">
        <button onclick="scaricaSms(true)">⬇️ Scarica SMS campagna arretrato</button>
        <button onclick="segnaSms(true)">✔️ Segna campagna inviata</button>
      </span>
    </div>
    <div id="note-conteggio"></div>
    <div id="barra-selezione" style="display:none;background:#23395d;color:#fff;border-radius:8px;padding:8px 14px;margin-bottom:10px">
      <b><span id="n-selezionati">0</span> selezionati</b>
      <button onclick="aggiungiACoda('sms')" style="margin-left:12px">✉️ Metti in coda SMS</button>
      <button onclick="aggiungiACoda('brevo')" style="margin-left:6px">📧 Metti in coda Brevo</button>
      <button onclick="SELEZIONE.clear(); mostraChiamate()" style="margin-left:6px">Annulla selezione</button>
    </div>
    <table id="tabella-chiamate">
      <thead><tr><th><input type="checkbox" id="sel-tutti" title="Seleziona tutti i visibili"></th><th>Stato</th><th>Scadenza</th><th>Immatricolazione</th><th>Cliente</th><th>Telefono</th><th>Veicolo</th><th>Segnalazioni</th><th>Azioni</th></tr></thead>
      <tbody></tbody>
    </table>
  </section>
  <section id="tab-recupero" style="display:none">
    <div id="note-recupero" class="muted" style="margin-bottom:8px">Clienti storici rimasti senza veicolo in scadenzario: chiedere che auto guidano ora.</div>
    <table id="tabella-recupero">
      <thead><tr><th>Cliente</th><th>Telefono</th><th>Ultimo veicolo</th><th>Targa / Telaio</th><th>Motivo</th><th>Quando / Fonte</th><th>Azioni</th></tr></thead>
      <tbody></tbody>
    </table>
  </section>
  <section id="tab-invii" style="display:none">
    <h3 style="margin:6px 0">✉️ Coda SMS (smscafè) — <span id="n-coda-sms">0</span> in coda</h3>
    <div class="filtri">
      <button onclick="window.location='/api/coda.xlsx?canale=sms'">⬇️ Esporta Excel per smscafè</button>
      <button onclick="segnaCodaInviata('sms')">✔️ Segna coda inviata oggi</button>
      <button onclick="svuotaCoda('sms')">🗑 Svuota coda</button>
    </div>
    <table id="tabella-coda-sms" style="margin-bottom:26px"><thead><tr><th>Cliente</th><th>Telefono</th><th>Veicolo</th><th>Scadenza</th><th>In coda dal</th><th>Inviato il</th><th></th></tr></thead><tbody></tbody></table>
    <h3 style="margin:6px 0">📧 Coda Brevo (email) — <span id="n-coda-brevo">0</span> in coda</h3>
    <div class="filtri">
      <button onclick="window.location='/api/coda.csv?canale=brevo'">⬇️ Esporta CSV per Brevo</button>
      <button onclick="segnaCodaInviata('brevo')">✔️ Segna coda inviata oggi</button>
      <button onclick="svuotaCoda('brevo')">🗑 Svuota coda</button>
    </div>
    <table id="tabella-coda-brevo"><thead><tr><th>Cliente</th><th>Email</th><th>Veicolo</th><th>Scadenza</th><th>In coda dal</th><th>Inviato il</th><th></th></tr></thead><tbody></tbody></table>
  </section>
  <section id="tab-filtri" style="display:none">
    <h3 style="margin:6px 0">🏪 Punti vendita / segnalatori</h3>
    <div class="muted" style="margin-bottom:6px">Gli esclusi non compaiono in nessuna lista (i dati restano in archivio).</div>
    <table id="tabella-pv" style="margin-bottom:22px"><thead><tr><th>Codice</th><th>Descrizione</th><th>Veicoli</th><th>Stato</th><th>Azione</th></tr></thead><tbody></tbody></table>
    <h3 style="margin:6px 0">🚛 Flotte (clienti con 4+ veicoli attivi)</h3>
    <div class="muted" style="margin-bottom:6px">Le flotte sono escluse da SMS e liste chiamate.</div>
    <table id="tabella-flotte" style="margin-bottom:22px"><thead><tr><th>Cliente</th><th>Veicoli attivi</th><th>Stato</th><th>Azione</th></tr></thead><tbody></tbody></table>
    <h3 style="margin:6px 0">🔀 Varianti dello stesso soggetto (GFC / G.F.C. SRL, ES MOBILITY / ES MOB…)</h3>
    <div class="muted" style="margin-bottom:6px">Stesso nucleo del nome al netto di punteggiatura e forme societarie: probabilmente è un cliente solo scritto in modi diversi. Solo soggetti aziendali.</div>
    <table id="tabella-varianti" style="margin-bottom:22px"><thead><tr><th>Gruppo</th><th>Schede (veicoli attivi/totali)</th><th>Azioni</th></tr></thead><tbody></tbody></table>
    <h3 style="margin:6px 0">👥 Possibili clienti duplicati (stesso nome)</h3>
    <div class="muted" style="margin-bottom:6px">Decidi tu: unisci in un cliente solo, oppure dichiara che sono persone diverse (non verranno più proposti).</div>
    <table id="tabella-omonimi" style="margin-bottom:22px"><thead><tr><th>Nome</th><th>Schede</th><th>Dettaglio (telefono — veicoli)</th><th>Azioni</th></tr></thead><tbody></tbody></table>
    <h3 style="margin:6px 0">🚗 Sospetti doppioni veicolo (telaio da una fonte, targa da un'altra)</h3>
    <div class="muted" style="margin-bottom:6px">Stesso cliente (a meno di grafie diverse), stesso mese di immatricolazione: probabilmente è un veicolo solo. Unendoli, telaio, targa e telefono si ricompongono.</div>
    <table id="tabella-doppioni"><thead><tr><th>Cliente</th><th>Scheda con telaio</th><th>Scheda con targa</th><th>Azioni</th></tr></thead><tbody></tbody></table>
  </section>
  <section id="tab-cerca" style="display:none">
    <div class="filtri"><input type="search" id="cerca-cliente" placeholder="Nome, telefono, targa o telaio… (min 3 caratteri)"></div>
    <div id="risultati-cerca"></div>
  </section>
  <section id="tab-stat" style="display:none">
    <div id="stat-vuoto" class="muted" style="display:none">Nessun dato della linea revisioni: importa l'export PDF del portale Dekra con "⬆️ Aggiorna dati" (o da terminale: importa-dekra).</div>
    <div id="stat-contenuto" style="display:none">
      <div class="kpi-griglia" id="stat-kpi"></div>
      <div class="grafico-card">
        <h3>Revisioni fatte in linea, mese per mese</h3>
        <div class="muted" id="stat-mensile-nota"></div>
        <div class="grafico" id="graf-mensile"></div>
        <div class="mesi" id="mesi-mensile"></div>
        <div class="legenda"><span><i style="background:#2a78d6"></i>Parco nostro</span><span><i style="background:#eb6834"></i>Veicoli esterni</span></div>
      </div>
      <div class="grafico-card">
        <h3>Potenziale ritorni nei prossimi 12 mesi</h3>
        <div class="muted">Targhe già passate da noi la cui prossima revisione (ultima REGOLARE + 2 anni) cade nel mese indicato.</div>
        <div class="grafico" id="graf-potenziale"></div>
        <div class="mesi" id="mesi-potenziale"></div>
        <div class="legenda"><span><i style="background:#2a78d6"></i>Parco nostro</span><span><i style="background:#eb6834"></i>Veicoli esterni</span></div>
      </div>
      <details class="grafico-card"><summary style="cursor:pointer;font-size:14px">📋 Dati in tabella</summary>
        <table id="stat-tabella" style="margin-top:10px;box-shadow:none"><thead><tr><th>Mese</th><th>Revisioni fatte</th><th>di cui parco nostro</th><th>di cui esterni</th></tr></thead><tbody></tbody></table>
      </details>
    </div>
  </section>
</main>
<script>
let CHIAMATE = [], FILTRO = 'MESE_CORRENTE', MESE = '', SELEZIONE = new Set();

async function api(percorso, corpo) {
  const opz = corpo ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(corpo)} : {};
  const r = await fetch(percorso, opz);
  return r.json();
}

function esc(s) { return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;'); }

async function carica() {
  const r = await api('/api/riepilogo');
  document.getElementById('k-sms').textContent = r.sms;
  document.getElementById('k-chiamate').textContent = r.chiamate;
  document.getElementById('k-mese').textContent = r.mese_corrente;
  document.getElementById('k-cold').textContent = r.cold;
  document.getElementById('k-dati').textContent = r.dati_mancanti;
  document.getElementById('k-recupero').textContent = r.da_recuperare;
  document.getElementById('k-lead').textContent = r.lead;
  await caricaChiamate();
}

async function caricaChiamate() {
  CHIAMATE = (await api('/api/chiamate' + (MESE ? '?mese=' + MESE : ''))).chiamate;
  mostraChiamate();
}

document.getElementById('file-aggiorna').addEventListener('change', async e => {
  const files = [...e.target.files];
  if (!files.length) return;
  const btn = document.getElementById('btn-aggiorna');
  btn.disabled = true; btn.textContent = '⏳ Importo…';
  const esiti = [];
  for (const f of files) {
    const b64 = await new Promise(ok => {
      const r = new FileReader();
      r.onload = () => ok(r.result.split(',')[1]);
      r.readAsDataURL(f);
    });
    try {
      const r = await api('/api/aggiorna', {nome: f.name, contenuto: b64});
      esiti.push(f.name + ': ' + (r.dettaglio || r.errore || 'ok'));
    } catch (err) {
      esiti.push(f.name + ': errore di caricamento');
    }
  }
  btn.disabled = false; btn.textContent = '⬆️ Aggiorna dati';
  e.target.value = '';
  alert('Import completato:\\n\\n' + esiti.join('\\n'));
  carica();
});

function aggiornaBarra() {
  document.getElementById('barra-selezione').style.display = SELEZIONE.size ? '' : 'none';
  document.getElementById('n-selezionati').textContent = SELEZIONE.size;
}
function toggleSel(id, on) { on ? SELEZIONE.add(id) : SELEZIONE.delete(id); aggiornaBarra(); }
async function aggiungiACoda(canale) {
  const r = await api('/api/coda', {veicolo_ids: [...SELEZIONE], canale});
  alert(r.messaggio);
  SELEZIONE.clear();
  carica();
}
async function segnaCodaInviata(canale) {
  if (!confirm('Confermo: la coda ' + canale.toUpperCase() + ' è stata inviata oggi?')) return;
  const r = await api('/api/coda-inviata', {canale});
  alert(r.messaggio);
  caricaInvii(); carica();
}
async function svuotaCoda(canale) {
  if (!confirm('Svuoto la coda ' + canale.toUpperCase() + '? (le voci non ancora inviate escono dalla coda; gli invii già registrati restano nello storico)')) return;
  const r = await api('/api/coda-svuota', {canale});
  alert(r.messaggio);
  caricaInvii(); carica();
}
async function rimuoviDaCoda(id) { await api('/api/coda-rimuovi', {id}); caricaInvii(); carica(); }
async function caricaInvii() {
  const r = await api('/api/code');
  for (const canale of ['sms', 'brevo']) {
    const righe = r[canale];
    document.getElementById('n-coda-' + canale).textContent = righe.filter(x => !x.inviato_il).length;
    document.querySelector('#tabella-coda-' + canale + ' tbody').innerHTML = righe.map(x => `
      <tr style="${x.inviato_il ? 'opacity:.55' : ''}"><td><b>${esc(x.cliente)}</b></td>
      <td>${esc(canale === 'sms' ? x.telefono : x.email) || '<span class="badge b-tel">mancante</span>'}</td>
      <td>${esc((x.marca + ' ' + (x.modello || '')).trim())} ${esc(x.targa || x.telaio)}</td>
      <td>${x.scadenza || ''}</td><td>${(x.aggiunto_il || '').slice(0, 10)}</td>
      <td>${x.inviato_il ? '✔️ ' + x.inviato_il.slice(0, 10) : '<span class="muted">in coda</span>'}</td>
      <td>${x.inviato_il ? '' : '<button class="btn-tel" title="Togli dalla coda" onclick="rimuoviDaCoda(' + x.id + ')">🗑</button>'}</td></tr>`).join('')
      || '<tr><td colspan="7" class="muted">Coda vuota: seleziona i clienti dalla lista chiamate.</td></tr>';
  }
}

async function scaricaSms(arretrato) {
  window.location = '/api/sms.xlsx' + (arretrato ? '?arretrato=1' : '');
}
async function segnaSms(arretrato) {
  if (!confirm('Registro "sms inviato" su tutti i veicoli della lista corrente?')) return;
  const r = await api('/api/sms-segna', {arretrato});
  alert(r.messaggio);
  carica();
}

function mostraChiamate() {
  const q = document.getElementById('cerca-chiamate').value.toLowerCase();
  document.getElementById('strumenti-sms').style.display = FILTRO === 'SMS' ? '' : 'none';
  document.getElementById('strumenti-arretrato').style.display = (FILTRO === 'COLD' || FILTRO === 'RISCALDA') ? '' : 'none';
  let sel = MESE ? CHIAMATE.filter(c => c.fase !== 'DATI_MANCANTI') : CHIAMATE.filter(c =>
    FILTRO === 'LEAD' ? c.lead :
    FILTRO === 'COLD' ? (c.fase === 'ARRETRATO' && c.mai_contattato) :
    FILTRO === 'RISCALDA' ? c.fase === 'ARRETRATO' :
    FILTRO === 'DATI' ? c.fase === 'DATI_MANCANTI' :
    c.fase === FILTRO);
  if (q) sel = sel.filter(c => (c.cliente + c.targa + c.telaio + c.telefono).toLowerCase().includes(q));
  const clientiUnici = new Set(sel.map(c => c.cliente)).size;
  document.getElementById('note-conteggio').textContent =
    (MESE ? 'Scadenze di ' + MESE + ': ' : '') + sel.length + ' veicoli di ' + clientiUnici + ' clienti' +
    (sel.length > 400 ? ' (mostro i primi 400)' : '') +
    (FILTRO === 'DATI' && !MESE ? " — manca la data: chiedi al cliente quando ha fatto l'ultima revisione e premi \\"Revisione fatta\\", il veicolo entra in scadenzario" : '') +
    (FILTRO === 'COLD' && !MESE ? ' — scadenza superata e mai contattati finora' : '') +
    (FILTRO === 'RISCALDA' && !MESE ? ' — scaduti da tempo: revisione probabilmente fatta altrove o auto cambiata. Seleziona e metti in coda SMS/Brevo, oppure chiama: se ha cambiato auto usa "Auto venduta" e registra la nuova' : '');
  const tb = document.querySelector('#tabella-chiamate tbody');
  tb.innerHTML = sel.slice(0, 400).map(c => `
    <tr class="${c.stato}">
      <td><input type="checkbox" ${SELEZIONE.has(c.veicolo_id) ? 'checked' : ''} onchange="toggleSel(${c.veicolo_id}, this.checked)"></td>
      <td><span class="stato">${c.stato.replace('_',' ')}</span>
          ${c.in_coda ? c.in_coda.map(k => '<div><span class="badge b-lead">📤 coda ' + k + '</span></div>').join('') : ''}</td>
      <td>${c.scadenza || '<span class="muted">da scoprire</span>'}<div class="muted">${c.giorni === null || c.giorni === undefined ? '' : c.giorni >= 0 ? 'tra ' + c.giorni + ' gg' : Math.abs(c.giorni) + ' gg fa'}</div></td>
      <td>${c.immatricolazione || '—'}${c.fonte_data === 'presunta' ? '<div class="muted">presunta</div>' : ''}
          ${c.ultima_revisione ? '<div class="muted">ult. rev. ' + c.ultima_revisione + '</div>' : ''}</td>
      <td><b>${esc(c.cliente)}</b></td>
      <td>${esc(c.telefono)}
          <button class="btn-tel" title="Correggi telefono" onclick="modificaTelefono(${c.veicolo_id}, '${esc(c.telefono).replace(/'/g, '')}')">✏️</button>
          ${['sospetto','non_valido','mancante'].includes(c.telefono_stato)
            ? '<div><span class="badge b-tel">☎️ ' + (c.telefono_stato === 'mancante' ? 'telefono mancante' : 'tel. ' + c.telefono_stato.replace('_',' ') + (c.telefono_motivo ? ': ' + esc(c.telefono_motivo) : '')) + '</span></div>' : ''}</td>
      <td>${esc((c.marca + ' ' + c.modello).trim())} ${esc(c.targa)}<div class="muted">${esc(c.telaio)}</div>
          ${c.fonte_file ? '<div class="muted">📄 ' + esc(c.fonte_file) + '</div>' : ''}</td>
      <td>${c.lead ? '<span class="badge b-lead">LEAD TCAR</span>' : ''}
          ${c.avviso ? '<span class="badge b-avviso">cambio auto?</span>' : ''}
          ${c.fase === 'ARRETRATO' ? '<span class="badge b-avviso">♻️ possibile nuovo veicolo</span>' : ''}
          ${FILTRO === 'RISCALDA' && !c.ha_email ? '<span class="badge b-tel">senza email</span>' : ''}
          ${c.ultimo_esito ? '<span class="badge b-esito">' + esc(c.ultimo_esito) + '</span>' : ''}</td>
      <td><div class="azioni">
        <button onclick="segnaEsito(${c.veicolo_id}, 'contattato')">Contattato</button>
        <button onclick="segnaEsito(${c.veicolo_id}, 'appuntamento')">Appuntamento</button>
        <button onclick="revisioneFatta(${c.veicolo_id})">Revisione fatta</button>
        <button onclick="segnaEsito(${c.veicolo_id}, 'irraggiungibile')">Non risponde</button>
        <button onclick="nonPossiede(${c.veicolo_id})">Auto venduta</button>
      </div></td>
    </tr>`).join('');
}

async function modificaTelefono(veicoloId, attuale) {
  const nuovo = prompt('Nuovo numero di telefono (quello attuale verrà sostituito):', attuale);
  if (nuovo === null) return;
  const r = await api('/api/telefono', {veicolo_id: veicoloId, telefono: nuovo.trim()});
  if (r.avvertenza && !confirm(r.avvertenza + '\\nSalvo comunque?')) return;
  if (r.avvertenza) await api('/api/telefono', {veicolo_id: veicoloId, telefono: nuovo.trim(), forza: true});
  carica();
}

async function segnaEsito(id, esito) {
  const note = prompt('Note (facoltative):', '') ?? '';
  const r = await api('/api/esito', {veicolo_id: id, esito, note});
  if (r.avviso_recupero) alert(r.avviso_recupero);
  carica();
}
async function revisioneFatta(id) {
  const oggi = new Date().toISOString().slice(0,10);
  const data = prompt('Data revisione (AAAA-MM-GG):', oggi);
  if (!data) return;
  const r = await api('/api/esito', {veicolo_id: id, esito: 'revisione_fatta', data});
  alert(r.messaggio || 'Registrata.');
  carica();
}
async function nonPossiede(id) {
  if (!confirm('Confermi che il cliente non possiede più questo veicolo?')) return;
  const note = prompt('Note (es. che auto ha ora?):', '') ?? '';
  const r = await api('/api/esito', {veicolo_id: id, esito: 'non_possiede_piu', note});
  if (r.avviso_recupero) alert(r.avviso_recupero);
  carica();
}

async function caricaRecupero() {
  const r = await api('/api/recuperare');
  document.querySelector('#tabella-recupero tbody').innerHTML = r.clienti.map(c => `
    <tr><td><b>${esc(c.nome)}</b></td>
    <td>${esc(c.telefono)}
        <button class="btn-tel" title="Correggi telefono" onclick="modificaTelefonoCliente(${c.id}, '${esc(c.telefono || '').replace(/'/g, '')}')">✏️</button>
        ${['sospetto','non_valido','mancante'].includes(c.telefono_stato)
          ? '<div><span class="badge b-tel">☎️ ' + (c.telefono_stato === 'mancante' ? 'telefono mancante' : 'tel. ' + c.telefono_stato.replace('_',' ') + (c.telefono_motivo ? ': ' + esc(c.telefono_motivo) : '')) + '</span></div>' : ''}</td>
    <td>${esc(c.veicolo) || '<span class="muted">—</span>'}</td>
    <td>${c.targa ? '<b>' + esc(c.targa) + '</b>' : ''}${c.telaio ? '<div class="muted">' + esc(c.telaio) + '</div>' : ''}</td>
    <td>${c.motivo ? '<span class="badge b-avviso">' + esc(c.motivo) + '</span>' : '<span class="muted">—</span>'}</td>
    <td>${c.dismesso_il || ''}${c.fonte ? '<div class="muted">📄 ' + esc(c.fonte) + '</div>' : ''}</td>
    <td><div class="azioni"><button onclick="nuovoVeicolo(${c.id}, '${esc(c.nome).replace(/'/g, '')}')">➕ Registra nuova auto</button></div></td></tr>`).join('')
    || '<tr><td colspan="7" class="muted">Nessun cliente da recuperare.</td></tr>';
}

async function modificaTelefonoCliente(clienteId, attuale) {
  const nuovo = prompt('Nuovo numero di telefono:', attuale);
  if (nuovo === null) return;
  let r = await api('/api/telefono', {cliente_id: clienteId, telefono: nuovo.trim()});
  if (r.avvertenza) {
    if (!confirm(r.avvertenza + '\\nSalvo comunque?')) return;
    r = await api('/api/telefono', {cliente_id: clienteId, telefono: nuovo.trim(), forza: true});
  }
  caricaRecupero(); carica();
}

async function nuovoVeicolo(clienteId, nome) {
  const targa = prompt('Targa della nuova auto di ' + nome + ':'); if (!targa) return;
  const marca = prompt('Marca:', '') ?? '';
  const modello = prompt('Modello:', '') ?? '';
  const imm = prompt('Data immatricolazione (AAAA-MM-GG) — vuoto se non nota:', '') ?? '';
  const rev = imm ? '' : (prompt('Data ultima revisione (AAAA-MM-GG):', '') ?? '');
  const r = await api('/api/nuovo-veicolo', {cliente_id: clienteId, targa, marca, modello, imm, ultima_revisione: rev});
  alert(r.messaggio || r.errore || 'Fatto.');
  caricaRecupero(); carica();
}

async function caricaFiltri() {
  const r = await api('/api/filtri');
  document.querySelector('#tabella-pv tbody').innerHTML = r.punti_vendita.map(p => `
    <tr><td><b>${p.codice}</b></td><td>${esc(p.descrizione) || '<span class="muted">senza nome</span>'}</td>
    <td>${p.veicoli}</td>
    <td>${p.escluso ? '<span class="badge b-tel">ESCLUSO</span>' : '<span class="badge b-futura" style="background:#d9ead3;color:#274e13">attivo</span>'}</td>
    <td><div class="azioni"><button onclick="togglePv('${p.codice}', ${p.escluso ? 0 : 1})">${p.escluso ? 'Reincludi' : 'Escludi'}</button></div></td></tr>`).join('');
  document.querySelector('#tabella-flotte tbody').innerHTML = r.flotte.map(f => `
    <tr><td><b>${esc(f.nome)}</b></td><td>${f.veicoli}</td>
    <td>${f.flotta ? '<span class="badge b-tel">FLOTTA (esclusa)</span>' : '<span class="badge" style="background:#d9ead3;color:#274e13">nelle liste</span>'}</td>
    <td><div class="azioni"><button onclick="toggleFlotta(${f.id}, ${f.flotta ? 0 : 1})">${f.flotta ? 'Riporta nelle liste' : 'Marca come flotta'}</button></div></td></tr>`).join('')
    || '<tr><td colspan="4" class="muted">Nessun candidato.</td></tr>';
  document.querySelector('#tabella-omonimi tbody').innerHTML = r.omonimi.map(g => `
    <tr><td><b>${esc(g.nome)}</b></td><td>${g.membri.length}</td>
    <td>${g.membri.map(m => '<div class="muted">' + (esc(m.telefono) || 'senza tel.') + ' — ' + m.totali + ' veicoli (' + esc((m.mezzi || '').slice(0, 40)) + ')</div>').join('')}</td>
    <td><div class="azioni">
      <button onclick="decidiOmonimi('${esc(g.nome).replace(/'/g, '')}', 'unisci')">🔗 Unisci</button>
      <button onclick="decidiOmonimi('${esc(g.nome).replace(/'/g, '')}', 'ignora')">👥 Persone diverse</button>
    </div></td></tr>`).join('')
    || '<tr><td colspan="4" class="muted">Nessun duplicato da valutare.</td></tr>';
  document.querySelector('#tabella-varianti tbody').innerHTML = r.varianti.map(g => `
    <tr><td><b>${esc(g.chiave)}</b><div class="muted">${g.veicoli_totali} veicoli in totale</div></td>
    <td>${g.membri.map(m => '<div>' + esc(m.nome) + ' <span class="muted">(' + m.attivi + '/' + m.totali + (m.flotta ? ', flotta' : '') + (m.telefono ? ', ' + esc(m.telefono) : '') + ')</span></div>').join('')}</td>
    <td><div class="azioni">
      <button onclick="decidiVarianti('${g.chiave}', [${g.membri.map(m => m.id).join(',')}], 'unisci')">🔗 Stesso soggetto</button>
      <button onclick="decidiVarianti('${g.chiave}', [], 'ignora')">❌ Soggetti diversi</button>
    </div></td></tr>`).join('') || '<tr><td colspan="3" class="muted">Nessuna variante da valutare.</td></tr>';
  document.querySelector('#tabella-doppioni tbody').innerHTML =
    r.doppioni.map(rigaDoppione).join('') || '<tr><td colspan="4" class="muted">Nessun sospetto doppione.</td></tr>';
}
function rigaDoppione(d) {
  return `<tr><td><b>${esc(d.cliente_a)}</b>${d.cliente_a !== d.cliente_b ? '<div class="muted">vs ' + esc(d.cliente_b) + '</div>' : ''}</td>
    <td>${esc(d.modello_a)}<div class="muted">${esc(d.telaio)}</div><div class="muted">imm. ${d.imm_a || '?'} — 📄 ${esc(d.fonte_a)}</div></td>
    <td>${esc(d.modello_b)} <b>${esc(d.targa)}</b><div class="muted">imm. ${d.imm_b || '?'} — 📄 ${esc(d.fonte_b)}</div></td>
    <td><div class="azioni">
      <button onclick="decidiDoppione('${d.chiave}', ${d.id_telaio}, ${d.id_targa}, 'unisci')">🔗 Stesso veicolo</button>
      <button onclick="decidiDoppione('${d.chiave}', ${d.id_telaio}, ${d.id_targa}, 'ignora')">❌ Veicoli diversi</button>
    </div></td></tr>`;
}
async function decidiDoppione(chiave, idTelaio, idTarga, azione) {
  if (azione === 'unisci' && !confirm('Confermo: sono lo stesso veicolo, unisco le due schede?')) return;
  const r = await api('/api/doppioni', {chiave, id_telaio: idTelaio, id_targa: idTarga, azione});
  if (r.messaggio) alert(r.messaggio);
  caricaFiltri(); carica();
}
async function decidiVarianti(chiave, ids, azione) {
  if (azione === 'unisci' && !confirm('Unisco tutte queste schede in un cliente solo?')) return;
  const r = await api('/api/varianti', {chiave, ids, azione});
  if (r.messaggio) alert(r.messaggio);
  caricaFiltri(); carica();
}
async function togglePv(codice, escluso) { await api('/api/pv', {codice, escluso}); caricaFiltri(); carica(); }
async function toggleFlotta(id, flotta) { await api('/api/flotta', {cliente_id: id, flotta}); caricaFiltri(); carica(); }
async function decidiOmonimi(nome, azione) {
  if (azione === 'unisci' && !confirm('Unisco tutte le schede "' + nome + '" in un cliente solo?')) return;
  const r = await api('/api/omonimi', {nome, azione});
  if (r.messaggio) alert(r.messaggio);
  caricaFiltri(); carica();
}

let timerCerca;
document.getElementById('cerca-cliente').addEventListener('input', e => {
  clearTimeout(timerCerca);
  timerCerca = setTimeout(async () => {
    const q = e.target.value.trim();
    if (q.length < 3) { document.getElementById('risultati-cerca').innerHTML = ''; return; }
    const r = await api('/api/cerca?q=' + encodeURIComponent(q));
    document.getElementById('risultati-cerca').innerHTML = r.clienti.map(c => `
      <div class="cliente-card">
        <b>${esc(c.nome)}</b> <span class="muted">${esc(c.telefono)} ${esc(c.email)}</span>
        ${c.veicoli.map(v => `<div style="margin:6px 0 0 10px">
          ${v.attivo ? '🚗' : '⚪️'} ${esc((v.marca + ' ' + v.modello).trim())} ${esc(v.targa)} <span class="muted">${esc(v.telaio)}</span>
          ${v.scadenza ? '— revisione entro <b>' + v.scadenza + '</b>' : (v.archiviato ? '<span class="muted">(archiviato)</span>' : (v.attivo ? '' : '<span class="muted">(dismesso)</span>'))}
          ${v.eventi.map(ev => '<div class="muted" style="margin-left:22px">• ' + esc(ev) + '</div>').join('')}
        </div>`).join('')}
      </div>`).join('') || '<div class="muted">Nessun risultato.</div>';
  }, 300);
});

const MESI_IT = ['gen','feb','mar','apr','mag','giu','lug','ago','set','ott','nov','dic'];
function etichettaMese(iso) { return MESI_IT[parseInt(iso.slice(5,7),10)-1] + " '" + iso.slice(2,4); }

function disegnaBarre(serie, idGrafico, idMesi, passo) {
  const max = Math.max(1, ...serie.map(x => x.nostri + x.esterni));
  document.getElementById(idGrafico).innerHTML = serie.map(x => {
    const tot = x.nostri + x.esterni;
    let seg = '';
    if (x.esterni) seg += '<div class="seg-esterni" style="height:' + Math.max(1, Math.round(x.esterni / max * 100)) + '%"></div>';
    if (x.nostri) seg += '<div class="seg-nostri" style="height:' + Math.max(1, Math.round(x.nostri / max * 100)) + '%"></div>';
    return '<div class="colonna" title="' + etichettaMese(x.mese) + ' — ' + tot + ' revisioni: ' +
           x.nostri + ' parco nostro, ' + x.esterni + ' esterni">' + seg + '</div>';
  }).join('');
  document.getElementById(idMesi).innerHTML = serie.map((x, i) =>
    '<span>' + (i % passo === 0 ? etichettaMese(x.mese) : '') + '</span>').join('');
}

async function caricaStat() {
  const r = await api('/api/dekra');
  document.getElementById('stat-vuoto').style.display = r.vuoto ? '' : 'none';
  document.getElementById('stat-contenuto').style.display = r.vuoto ? 'none' : '';
  if (r.vuoto) return;
  const it = d => d.slice(8,10) + '/' + d.slice(5,7) + '/' + d.slice(0,4);
  const pctNostri = Math.round(r.passaggi_nostri / r.passaggi * 100);
  const ultimi12 = r.mensile.slice(-13, -1);
  const media12 = ultimi12.length ? Math.round(ultimi12.reduce((s, x) => s + x.nostri + x.esterni, 0) / ultimi12.length) : 0;
  const arretrati = r.arretrato.nostri + r.arretrato.esterni;
  document.getElementById('stat-kpi').innerHTML = `
    <div class="kpi"><span class="muted">Revisioni fatte in linea</span><b>${r.passaggi}</b><span class="muted">dal ${it(r.dal)} al ${it(r.al)}</span></div>
    <div class="kpi"><span class="muted">Veicoli distinti passati</span><b>${r.targhe}</b><span class="muted">media ${media12} revisioni/mese (ultimi 12)</span></div>
    <div class="kpi"><span class="muted">Dal nostro parco clienti</span><b>${r.passaggi_nostri} <small style="font-size:14px">(${pctNostri}%)</small></b><span class="muted">${r.targhe_nostre} veicoli</span></div>
    <div class="kpi"><span class="muted">Da fuori (solo revisione)</span><b>${r.passaggi_esterni} <small style="font-size:14px">(${100 - pctNostri}%)</small></b><span class="muted">${r.targhe_esterne} veicoli: candidati tagliandi</span></div>
    <div class="kpi"><span class="muted">Clienti fidelizzati</span><b>${r.fidelizzate}</b><span class="muted">targhe con 2+ revisioni da noi</span></div>
    <div class="kpi"><span class="muted">Non tornati (scaduti)</span><b>${arretrati}</b><span class="muted">${r.arretrato.nostri} parco nostro, ${r.arretrato.esterni} esterni: da richiamare</span></div>`;
  document.getElementById('stat-mensile-nota').textContent =
    'Ogni passaggio in linea documentato dal portale Dekra (esiti REGOLARI e non).';
  disegnaBarre(r.mensile, 'graf-mensile', 'mesi-mensile', 4);
  disegnaBarre(r.potenziale, 'graf-potenziale', 'mesi-potenziale', 2);
  document.querySelector('#stat-tabella tbody').innerHTML = r.mensile.map(x =>
    '<tr><td>' + etichettaMese(x.mese) + '</td><td>' + (x.nostri + x.esterni) + '</td><td>' +
    x.nostri + '</td><td>' + x.esterni + '</td></tr>').join('');
}

document.querySelectorAll('nav button').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('nav button').forEach(x => x.classList.remove('attivo'));
  b.classList.add('attivo');
  ['chiamate','recupero','cerca','invii','stat','filtri'].forEach(t => document.getElementById('tab-' + t).style.display = (t === b.dataset.tab ? '' : 'none'));
  if (b.dataset.tab === 'recupero') caricaRecupero();
  if (b.dataset.tab === 'filtri') caricaFiltri();
  if (b.dataset.tab === 'invii') caricaInvii();
  if (b.dataset.tab === 'stat') caricaStat();
}));
document.querySelectorAll('.filtri button[data-f]').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('.filtri button[data-f]').forEach(x => x.classList.remove('attivo'));
  b.classList.add('attivo'); FILTRO = b.dataset.f;
  if (MESE) { MESE = ''; document.getElementById('mese-futuro').value = ''; caricaChiamate(); }
  else mostraChiamate();
}));
document.getElementById('cerca-chiamate').addEventListener('input', mostraChiamate);
document.getElementById('sel-tutti').addEventListener('change', e => {
  document.querySelectorAll('#tabella-chiamate tbody input[type=checkbox]').forEach(cb => {
    cb.checked = e.target.checked;
    cb.dispatchEvent(new Event('change'));
  });
});
document.getElementById('mese-futuro').addEventListener('change', e => {
  MESE = e.target.value || '';
  document.querySelectorAll('.filtri button[data-f]').forEach(x => x.classList.toggle('attivo', !MESE && x.dataset.f === FILTRO));
  caricaChiamate();
});
carica();
</script>
</body>
</html>
"""


def _json(handler: BaseHTTPRequestHandler, dati, codice=200):
    corpo = json.dumps(dati, ensure_ascii=False).encode("utf-8")
    handler.send_response(codice)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(corpo)))
    handler.end_headers()
    handler.wfile.write(corpo)


def crea_handler(percorso_db: Path):
    # Connessione unica (le richieste sono serializzate da _lock) e cache dei
    # calcoli pesanti, invalidata a ogni scrittura.
    conn_condivisa = database.apri_db(percorso_db, condivisa_tra_thread=True)
    cache: dict = {}

    def scadenze_cache(includi_esclusi: bool = False):
        chiave = "tutte" if includi_esclusi else "attive"
        if chiave not in cache:
            cache[chiave] = calcola_scadenze(conn_condivisa, includi_esclusi=includi_esclusi)
        return cache[chiave]

    def recupero_cache():
        if "recupero" not in cache:
            cache["recupero"] = database.clienti_senza_veicolo(conn_condivisa)
        return cache["recupero"]

    def dati_mancanti_cache():
        # Veicoli fuori gestione senza data: in lista solo se chiamabili.
        if "dati_mancanti" not in cache:
            from .telefoni import valuta_campo
            righe = []
            for r in database.veicoli_dati_mancanti(conn_condivisa):
                stato_tel, _, motivo = valuta_campo(r["telefono"] or "")
                if stato_tel not in ("cellulare", "fisso"):
                    continue
                righe.append({
                    "veicolo_id": r["veicolo_id"], "stato": "DATI_MANCANTI", "fase": "DATI_MANCANTI",
                    "scadenza": "", "immatricolazione": "", "fonte_data": "",
                    "ultima_revisione": "", "giorni": None,
                    "cliente": r["cliente"], "telefono": r["telefono"] or "",
                    "targa": r["targa"] or "", "telaio": r["telaio"] or "",
                    "marca": r["marca"] or "", "modello": r["modello"] or "",
                    "lead": "", "avviso": "", "ultimo_esito": "",
                    "telefono_stato": stato_tel, "telefono_motivo": motivo,
                    "fonte_file": r["file_origine"] or "", "in_coda": [],
                    "mai_contattato": True,
                })
            righe.sort(key=lambda x: (x["telefono_stato"] != "cellulare", x["cliente"]))
            cache["dati_mancanti"] = righe
        return cache["dati_mancanti"]

    def invalida():
        cache.clear()

    class Handler(BaseHTTPRequestHandler):

        def log_message(self, *a):
            pass

        def _conn(self) -> sqlite3.Connection:
            return conn_condivisa

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/":
                corpo = PAGINA.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)
                return
            with _lock:
                conn = self._conn()
                try:
                    if url.path == "/api/riepilogo":
                        lista = da_contattare(scadenze_cache())
                        lead = conn.execute("SELECT COUNT(*) AS n FROM lead_tcar WHERE veicolo_id IS NOT NULL").fetchone()["n"]
                        _json(self, {
                            "sms": sum(1 for s in lista if s.fase == "SMS" and s.ultimo_esito != "sms_inviato"),
                            "chiamate": sum(1 for s in lista if s.fase == "CHIAMATA"),
                            "mese_corrente": sum(1 for s in lista if s.fase == "MESE_CORRENTE"),
                            "cold": sum(1 for s in lista if s.fase == "ARRETRATO" and s.mai_contattato),
                            "dati_mancanti": len(dati_mancanti_cache()),
                            "da_recuperare": len(recupero_cache()),
                            "lead": lead,
                        })
                    elif url.path == "/api/chiamate":
                        mese = parse_qs(url.query).get("mese", [""])[0]
                        if mese:
                            # Interrogazione libera: tutte le scadenze di quel mese
                            # (anche future oltre le fasi operative), esclusi i gestiti.
                            lista = [s for s in scadenze_cache()
                                     if s.scadenza and s.scadenza.strftime("%Y-%m") == mese
                                     and s.ultimo_esito not in ("appuntamento", "non_interessato")]
                            lista.sort(key=lambda s: (s.scadenza, s.cliente))
                        else:
                            lista = da_contattare(scadenze_cache())
                        in_coda: dict[int, list] = {}
                        for r in conn.execute("SELECT veicolo_id, canale FROM code_invio WHERE inviato_il IS NULL"):
                            in_coda.setdefault(r["veicolo_id"], []).append(r["canale"])
                        _json(self, {"chiamate": [{
                            "veicolo_id": s.veicolo_id, "stato": s.stato, "fase": s.fase,
                            "scadenza": s.scadenza.strftime("%d/%m/%Y") if s.scadenza else "",
                            "immatricolazione": s.data_immatricolazione.strftime("%d/%m/%Y") if s.data_immatricolazione else "",
                            "fonte_data": "presunta" if s.fonte_data == "mese_report" else s.fonte_data,
                            "ultima_revisione": s.ultima_revisione.strftime("%d/%m/%Y") if s.ultima_revisione else "",
                            "giorni": s.giorni_rimanenti, "cliente": s.cliente,
                            "telefono": s.telefono, "targa": s.targa, "telaio": s.telaio,
                            "marca": s.marca, "modello": s.modello,
                            "lead": s.lead_tcar, "avviso": s.avviso, "ultimo_esito": s.ultimo_esito,
                            "telefono_stato": s.telefono_stato, "telefono_motivo": s.telefono_motivo,
                            "fonte_file": s.fonte_file,
                            "in_coda": in_coda.get(s.veicolo_id, []),
                            "mai_contattato": s.mai_contattato,
                            "ha_email": bool(s.email),
                        } for s in lista] + ([] if mese else dati_mancanti_cache())})
                    elif url.path == "/api/sms.xlsx":
                        from .sms import (TESTO_ARRETRATO_PREDEFINITO, TESTO_PREDEFINITO,
                                          _testo_template, crea_excel_smscafe, lista_sms)
                        arretrato = parse_qs(url.query).get("arretrato", ["0"])[0] == "1"
                        try:
                            righe = lista_sms(conn, arretrato=arretrato, base=percorso_db.parent.parent)
                        except ValueError as e:
                            return _json(self, {"errore": str(e)}, 400)
                        if arretrato:
                            template = _testo_template(percorso_db.parent / "sms_testo_arretrato.txt", TESTO_ARRETRATO_PREDEFINITO)
                        else:
                            template = _testo_template(percorso_db.parent / "sms_testo.txt", TESTO_PREDEFINITO)
                        corpo = crea_excel_smscafe(righe, template)
                        nome = "sms_arretrato_smscafe.xlsx" if arretrato else "sms_scadenze_smscafe.xlsx"
                        self.send_response(200)
                        self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                        self.send_header("Content-Disposition", f'attachment; filename="{nome}"')
                        self.send_header("Content-Length", str(len(corpo)))
                        self.end_headers()
                        self.wfile.write(corpo)
                    elif url.path == "/api/recuperare":
                        from .telefoni import valuta_campo
                        clienti = []
                        for r in recupero_cache():
                            d = dict(r)
                            d["telefono_stato"], _, d["telefono_motivo"] = valuta_campo(d.get("telefono") or "")
                            clienti.append(d)
                        _json(self, {"clienti": clienti})
                    elif url.path == "/api/code":
                        _json(self, {
                            "sms": [dict(r) for r in database.coda_invio(conn, "sms", solo_in_coda=False)[:400]],
                            "brevo": [dict(r) for r in database.coda_invio(conn, "brevo", solo_in_coda=False)[:400]],
                        })
                    elif url.path == "/api/coda.xlsx":
                        from datetime import date as date_mod

                        from .scadenze import ScadenzaVeicolo
                        from .sms import (TESTO_PREDEFINITO, _cellulare, _componi,
                                          _testo_template, controlla_template, crea_excel_smscafe)
                        righe_coda = database.coda_invio(conn, "sms", solo_in_coda=True)
                        testo = _testo_template(percorso_db.parent / "sms_testo.txt", TESTO_PREDEFINITO)
                        try:
                            controlla_template(testo)
                        except ValueError as e:
                            return _json(self, {"errore": str(e)}, 400)
                        righe = []
                        for r in righe_coda:
                            numero = _cellulare(r["telefono"] or "")
                            if not numero:
                                continue
                            finta = ScadenzaVeicolo(
                                veicolo_id=r["veicolo_id"], telaio=r["telaio"] or "",
                                marca=r["marca"] or "", modello=r["modello"] or "",
                                punto_vendita="", cliente=r["cliente"], telefono=numero,
                                data_immatricolazione=None, fonte_data="", ultima_revisione=None,
                                scadenza=date_mod.fromisoformat(r["scadenza"]) if r["scadenza"] else None,
                                giorni_rimanenti=None, stato="", ultimo_esito="",
                                targa=r["targa"] or "")
                            righe.append({"telefono": numero, "nome": r["cliente"],
                                          "targa": r["targa"] or "",
                                          "scadenza": (date_mod.fromisoformat(r["scadenza"]).strftime("%d/%m/%Y")
                                                       if r["scadenza"] else ""),
                                          "messaggio": _componi(testo, finta)})
                        corpo = crea_excel_smscafe(righe, testo)
                        self.send_response(200)
                        self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                        self.send_header("Content-Disposition", 'attachment; filename="coda_sms_smscafe.xlsx"')
                        self.send_header("Content-Length", str(len(corpo)))
                        self.end_headers()
                        self.wfile.write(corpo)
                    elif url.path == "/api/coda.csv":
                        canale = parse_qs(url.query).get("canale", ["sms"])[0]
                        righe = database.coda_invio(conn, canale, solo_in_coda=True)
                        import csv as csv_mod
                        import io
                        buf = io.StringIO()
                        w = csv_mod.writer(buf, delimiter=";")
                        if canale == "sms":
                            from .sms import TESTO_PREDEFINITO, _componi, _testo_template, _cellulare, controlla_template
                            from .scadenze import ScadenzaVeicolo
                            from datetime import date as date_mod
                            testo = _testo_template(percorso_db.parent / "sms_testo.txt", TESTO_PREDEFINITO)
                            try:
                                controlla_template(testo)
                            except ValueError as e:
                                corpo = str(e).encode("utf-8")
                                self.send_response(400)
                                self.send_header("Content-Type", "text/plain; charset=utf-8")
                                self.send_header("Content-Length", str(len(corpo)))
                                self.end_headers()
                                self.wfile.write(corpo)
                                return
                            w.writerow(["Telefono", "Nome", "Targa", "Scadenza", "Messaggio", "Caratteri"])
                            for r in righe:
                                numero = _cellulare(r["telefono"] or "")
                                if not numero:
                                    continue
                                finta = ScadenzaVeicolo(
                                    veicolo_id=r["veicolo_id"], telaio=r["telaio"] or "",
                                    marca=r["marca"] or "", modello=r["modello"] or "",
                                    punto_vendita="", cliente=r["cliente"], telefono=numero,
                                    data_immatricolazione=None, fonte_data="", ultima_revisione=None,
                                    scadenza=date_mod.fromisoformat(r["scadenza"]) if r["scadenza"] else None,
                                    giorni_rimanenti=None, stato="", ultimo_esito="",
                                    targa=r["targa"] or "")
                                msg = _componi(testo, finta)
                                w.writerow([numero, r["cliente"], r["targa"] or "", r["scadenza"] or "", msg, len(msg)])
                            nome_file = "coda_sms_smscafe.csv"
                        else:
                            w.writerow(["EMAIL", "NOME", "TARGA", "MODELLO", "SCADENZA_REVISIONE"])
                            for r in righe:
                                if not r["email"]:
                                    continue
                                w.writerow([r["email"], r["cliente"], r["targa"] or "",
                                            " ".join(filter(None, [r["marca"], r["modello"]])),
                                            r["scadenza"] or ""])
                            nome_file = "coda_brevo.csv"
                        corpo = ("﻿" + buf.getvalue()).encode("utf-8")
                        self.send_response(200)
                        self.send_header("Content-Type", "text/csv; charset=utf-8")
                        self.send_header("Content-Disposition", f'attachment; filename="{nome_file}"')
                        self.send_header("Content-Length", str(len(corpo)))
                        self.end_headers()
                        self.wfile.write(corpo)
                    elif url.path == "/api/filtri":
                        _json(self, {
                            "punti_vendita": [dict(r) for r in database.elenca_punti_vendita(conn)],
                            "flotte": [{"id": r["id"], "nome": r["nome"], "veicoli": r["veicoli"],
                                        "flotta": bool(r["flotta"])}
                                       for r in database.candidati_flotta(conn, soglia=4)],
                            "omonimi": database.gruppi_omonimi(conn)[:60],
                            "doppioni": database.trova_doppioni_veicoli(conn)[:80],
                            "varianti": database.gruppi_varianti_flotta(conn)[:60],
                        })
                    elif url.path == "/api/dekra":
                        _json(self, database.statistiche_dekra(conn))
                    elif url.path == "/api/cerca":
                        q = parse_qs(url.query).get("q", [""])[0].strip()
                        _json(self, {"clienti": self._cerca(conn, q, scadenze_cache(True))})
                    else:
                        _json(self, {"errore": "non trovato"}, 404)
                finally:
                    pass

        def do_POST(self):
            lunghezza = int(self.headers.get("Content-Length", 0))
            dati = json.loads(self.rfile.read(lunghezza) or b"{}")
            with _lock:
                conn = self._conn()
                try:
                    if self.path == "/api/esito":
                        self._esito(conn, dati)
                    elif self.path == "/api/nuovo-veicolo":
                        self._nuovo_veicolo(conn, dati)
                    elif self.path == "/api/pv":
                        database.imposta_esclusione(conn, str(dati["codice"]), bool(dati["escluso"]))
                        invalida()
                        _json(self, {"ok": True})
                    elif self.path == "/api/flotta":
                        database.imposta_flotta(conn, dati["cliente_id"], bool(dati["flotta"]))
                        invalida()
                        _json(self, {"ok": True})
                    elif self.path == "/api/coda":
                        ids = [int(i) for i in dati.get("veicolo_ids", [])]
                        canale = dati.get("canale", "sms")
                        scadenze_map = {s.veicolo_id: s.scadenza.isoformat() if s.scadenza else ""
                                        for s in scadenze_cache(True) if s.veicolo_id in set(ids)}
                        n = database.aggiungi_a_coda(conn, ids, canale, scadenze_map)
                        invalida()
                        _json(self, {"ok": True, "messaggio": f"{n} clienti aggiunti alla coda {canale.upper()}"
                                     + (f" ({len(ids) - n} erano già in coda)" if n < len(ids) else "") + "."})
                    elif self.path == "/api/coda-inviata":
                        n = database.segna_coda_inviata(conn, dati.get("canale", "sms"))
                        invalida()
                        _json(self, {"ok": True, "messaggio": f"Invio registrato per {n} clienti (data di oggi)."})
                    elif self.path == "/api/coda-svuota":
                        n = database.svuota_coda(conn, dati.get("canale", "sms"))
                        invalida()
                        _json(self, {"ok": True, "messaggio": f"Coda svuotata: {n} voci rimosse."})
                    elif self.path == "/api/coda-rimuovi":
                        database.rimuovi_da_coda(conn, int(dati.get("id", 0)))
                        invalida()
                        _json(self, {"ok": True})
                    elif self.path == "/api/aggiorna":
                        self._aggiorna(conn, dati, invalida)
                    elif self.path == "/api/varianti":
                        if dati.get("azione") == "unisci":
                            n = database.unisci_clienti(conn, dati.get("ids", []))
                            invalida()
                            _json(self, {"ok": True, "messaggio": f"Unite {n + 1} schede in un cliente solo."})
                        else:
                            database.ignora_varianti(conn, dati.get("chiave", ""))
                            _json(self, {"ok": True, "messaggio": "Registrato: sono soggetti diversi."})
                    elif self.path == "/api/doppioni":
                        if dati.get("azione") == "unisci":
                            database.unisci_veicoli(conn, dati["id_telaio"], dati["id_targa"])
                            invalida()
                            _json(self, {"ok": True, "messaggio": "Schede unite: telaio, targa e storico ora sono su un veicolo solo."})
                        else:
                            database.ignora_doppione(conn, dati.get("chiave", ""))
                            _json(self, {"ok": True, "messaggio": "Registrato: sono veicoli diversi."})
                    elif self.path == "/api/omonimi":
                        nome = dati.get("nome", "")
                        if dati.get("azione") == "unisci":
                            n = database.unisci_gruppo(conn, nome)
                            invalida()
                            _json(self, {"ok": True, "messaggio": f"Unite {n + 1} schede di {nome} in un cliente solo."})
                        else:
                            database.ignora_omonimi(conn, nome)
                            _json(self, {"ok": True, "messaggio": f"Registrato: gli omonimi '{nome}' sono persone diverse."})
                    elif self.path == "/api/telefono":
                        self._telefono(conn, dati)
                    elif self.path == "/api/sms-segna":
                        from .sms import lista_sms, segna_inviati
                        righe = lista_sms(conn, arretrato=bool(dati.get("arretrato")),
                                          base=percorso_db.parent.parent)
                        n = segna_inviati(conn, righe)
                        invalida()
                        _json(self, {"ok": True, "messaggio": f"Registrato 'sms inviato' su {n} veicoli."})
                    else:
                        _json(self, {"errore": "non trovato"}, 404)
                finally:
                    pass

        def _esito(self, conn, dati):
            veicolo_id = dati.get("veicolo_id")
            esito = dati.get("esito")
            note = (dati.get("note") or "").strip()
            row = conn.execute(
                "SELECT v.id, v.cliente_id, c.nome FROM veicoli v JOIN clienti c ON c.id = v.cliente_id WHERE v.id = ?",
                (veicolo_id,),
            ).fetchone()
            if not row:
                return _json(self, {"errore": "veicolo non trovato"}, 404)
            scadenze = {s.veicolo_id: s for s in scadenze_cache(True)}
            s = scadenze.get(veicolo_id)
            scadenza_iso = s.scadenza.isoformat() if s and s.scadenza else ""
            risposta = {"ok": True}
            if esito == "revisione_fatta":
                data_rev = date.fromisoformat(dati.get("data") or date.today().isoformat())
                database.registra_revisione(conn, veicolo_id, data_rev)
                invalida()
                nuove = scadenze_cache(True)
                prossima = next((x.scadenza for x in nuove if x.veicolo_id == veicolo_id), None)
                if prossima:
                    risposta["messaggio"] = f"Revisione registrata. Prossima chiamata: scadenza {prossima.strftime('%d/%m/%Y')}."
            elif esito == "non_possiede_piu":
                database.dismetti_veicolo(conn, veicolo_id)
                attivi = conn.execute(
                    "SELECT COUNT(*) AS n FROM veicoli WHERE cliente_id = ? AND attivo = 1",
                    (row["cliente_id"],),
                ).fetchone()["n"]
                if attivi == 0:
                    risposta["avviso_recupero"] = (f"{row['nome']} è rimasto senza veicoli in scadenzario: "
                                                   f"lo trovi nella scheda 'Da recuperare' per registrare la nuova auto.")
            database.registra_contatto(conn, veicolo_id, scadenza_iso, esito, note)
            invalida()
            _json(self, risposta)

        def _aggiorna(self, conn, dati, invalida_cache):
            import base64
            nome = Path(dati.get("nome", "file.xlsx")).name
            if not nome.lower().endswith((".xlsx", ".xls", ".pdf")):
                return _json(self, {"errore": "sono accettati file Excel (.xlsx/.xls) o il PDF del portale Dekra"}, 400)
            cartella = percorso_db.parent.parent / "import"
            cartella.mkdir(parents=True, exist_ok=True)
            percorso = cartella / nome
            percorso.write_bytes(base64.b64decode(dati.get("contenuto", "")))

            maiuscolo = nome.upper()
            try:
                if nome.lower().endswith(".pdf"):
                    from .parser_dekra import leggi_pdf_dekra
                    righe = leggi_pdf_dekra(percorso)
                    if not righe:
                        return _json(self, {"errore": "il PDF non sembra un export del portale Dekra"}, 400)
                    esito = database.importa_dekra(conn, righe, nome)
                    dettaglio = (f"Dekra: {esito['righe']} passaggi letti, {esito['nuove']} nuovi, "
                                 f"{esito['revisioni']} revisioni aggiunte allo storico, "
                                 f"{esito['non_agganciate']} di veicoli esterni")
                elif "ESTRAZIONELEADS" in maiuscolo.replace(" ", ""):
                    from .parser_tcar import leggi_export_lead
                    leads = leggi_export_lead(percorso)
                    esito = database.importa_lead_tcar(conn, leads, nome)
                    dettaglio = (f"lead Tcar: {esito['lead']} letti, {esito['match']} agganciati, "
                                 f"{esito['arricchiti']} veicoli arricchiti")
                elif "AXSCCF" in maiuscolo:
                    from .parser_ccf import leggi_report_ccf
                    righe, pv = leggi_report_ccf(percorso)
                    esito = database.importa_righe(conn, righe, nome, pv)
                    dettaglio = (f"WinDrakkar CCF: {esito['righe']} righe, {esito['nuovi']} veicoli nuovi, "
                                 f"{esito['aggiornati']} aggiornati")
                else:
                    from .parser_immatricolazioni import leggi_file_immatricolazioni
                    righe = leggi_file_immatricolazioni(percorso)
                    if righe:
                        esito = database.importa_immatricolazioni(conn, righe, nome)
                        dettaglio = (f"immatricolazioni: {esito['righe']} righe, "
                                     f"{esito['date_aggiornate']} date aggiornate, "
                                     f"{esito['nuovi']} veicoli nuovi, "
                                     f"{esito['targhe_aggiunte']} targhe aggiunte")
                        if esito["divergenze"]:
                            dettaglio += f", {len(esito['divergenze'])} divergenze data da verificare"
                    else:
                        return _json(self, {"errore": "formato non riconosciuto: il nome del file "
                                            "deve contenere mese e anno (es. AGOSTO 2026.xlsx)"}, 400)
                invalida_cache()
                _json(self, {"ok": True, "dettaglio": dettaglio})
            except Exception as e:
                _json(self, {"errore": f"import fallito: {str(e)[:120]}"}, 500)

        def _telefono(self, conn, dati):
            from .telefoni import valuta_campo
            cliente_id = dati.get("cliente_id")
            if not cliente_id:
                veicolo = conn.execute(
                    "SELECT cliente_id FROM veicoli WHERE id = ?", (dati.get("veicolo_id"),)
                ).fetchone()
                if not veicolo:
                    return _json(self, {"errore": "veicolo non trovato"}, 404)
                cliente_id = veicolo["cliente_id"]
            nuovo = (dati.get("telefono") or "").strip()
            stato, numero, motivo = valuta_campo(nuovo)
            # Se il numero è ancora anomalo chiedi conferma (a meno di forzatura).
            if stato not in ("cellulare", "fisso") and not dati.get("forza"):
                dettaglio = f"{stato.replace('_', ' ')}" + (f": {motivo}" if motivo else "")
                return _json(self, {"ok": False, "avvertenza": f"Il numero sembra ancora anomalo ({dettaglio})."})
            conn.execute(
                "UPDATE clienti SET telefono = ? WHERE id = ?",
                (numero if stato in ("cellulare", "fisso") else nuovo, cliente_id),
            )
            conn.commit()
            invalida()
            _json(self, {"ok": True})

        def _nuovo_veicolo(self, conn, dati):
            targa = (dati.get("targa") or "").strip().upper().replace(" ", "")
            if not targa:
                return _json(self, {"errore": "targa obbligatoria"}, 400)
            imm = dati.get("imm") or ""
            rev = dati.get("ultima_revisione") or ""
            if not imm and not rev:
                return _json(self, {"errore": "serve la data di immatricolazione o dell'ultima revisione"}, 400)
            veicolo_id = database.inserisci_veicolo_manuale(
                conn, dati["cliente_id"], targa, None,
                (dati.get("marca") or "").upper(), (dati.get("modello") or "").upper(),
                date.fromisoformat(imm) if imm else None)
            if rev:
                database.registra_revisione(conn, veicolo_id, date.fromisoformat(rev), fonte="dichiarata dal cliente")
            invalida()
            s = next((x for x in scadenze_cache(True) if x.veicolo_id == veicolo_id), None)
            msg = "Veicolo registrato."
            if s and s.scadenza:
                msg += f" Prossima revisione entro il {s.scadenza.strftime('%d/%m/%Y')}."
            _json(self, {"ok": True, "messaggio": msg})

        @staticmethod
        def _cerca(conn, q, scadenze_tutte):
            filtro = f"%{q}%"
            clienti = conn.execute(
                """SELECT DISTINCT c.* FROM clienti c
                   LEFT JOIN veicoli v ON v.cliente_id = c.id
                   WHERE c.nome LIKE ? OR c.telefono LIKE ? OR v.targa LIKE ? OR v.telaio LIKE ?
                   ORDER BY c.nome LIMIT 30""",
                (filtro, filtro, filtro, filtro),
            ).fetchall()
            scadenze = {s.veicolo_id: s for s in scadenze_tutte}
            out = []
            for c in clienti:
                veicoli = []
                for v in conn.execute(
                    "SELECT * FROM veicoli WHERE cliente_id = ? ORDER BY IFNULL(data_immatricolazione,'') DESC",
                    (c["id"],),
                ):
                    s = scadenze.get(v["id"])
                    eventi = [f"revisione il {r['data_revisione']} ({r['fonte']})" for r in conn.execute(
                        "SELECT data_revisione, fonte FROM revisioni_effettuate WHERE veicolo_id = ? ORDER BY data_revisione DESC LIMIT 3",
                        (v["id"],))]
                    eventi += [f"{k['data_contatto'][:10]}: {k['esito'].lower().replace('_', ' ')}" +
                               (f" — {k['note'][:60]}" if k["note"] else "") for k in conn.execute(
                        "SELECT data_contatto, esito, note FROM contatti WHERE veicolo_id = ? ORDER BY data_contatto DESC LIMIT 4",
                        (v["id"],))]
                    if v["file_origine"]:
                        eventi.append(f"fonte dati: {v['file_origine']}")
                    veicoli.append({
                        "marca": v["marca"] or "", "modello": v["modello"] or "",
                        "targa": v["targa"] or "", "telaio": v["telaio"] or "",
                        "attivo": bool(v["attivo"]) and not v["archiviato"],
                        "archiviato": bool(v["archiviato"]),
                        "scadenza": s.scadenza.strftime("%d/%m/%Y") if s and s.scadenza and v["attivo"] and not v["archiviato"] else "",
                        "eventi": eventi,
                    })
                out.append({"nome": c["nome"], "telefono": c["telefono"] or "",
                            "email": c["email"] or "", "veicoli": veicoli})
            return out

    return Handler


def avvia(percorso_db: Path, porta: int = 8765, apri_browser: bool = True, rete: bool = False) -> None:
    for esito in database.esegui_backup(percorso_db):
        print(f"Backup database → {esito}")
    host = "0.0.0.0" if rete else "127.0.0.1"
    indirizzo = f"http://127.0.0.1:{porta}"
    try:
        server = ThreadingHTTPServer((host, porta), crea_handler(percorso_db))
    except OSError:
        # Porta già occupata: la dashboard è già accesa, riapri solo il browser.
        print(f"La dashboard è già in esecuzione: apro {indirizzo}")
        if apri_browser:
            import webbrowser
            webbrowser.open(indirizzo)
        return
    # Uso da cartella condivisa: UNA postazione alla volta. Il lucchetto in
    # dati/ blocca l'apertura contemporanea da un altro PC (rischio corruzione).
    import getpass
    import socket
    import time
    lucchetto = percorso_db.parent / "in_uso.lock"
    postazione = f"{getpass.getuser()} su {socket.gethostname()}"
    if lucchetto.exists():
        try:
            eta = time.time() - lucchetto.stat().st_mtime
            occupante = lucchetto.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            eta, occupante = 9999, "?"
        stessa_postazione = socket.gethostname() in occupante
        if eta < 180 and not stessa_postazione:
            print("=" * 62)
            print(f"  ⚠ PROGRAMMA GIÀ IN USO da: {occupante}")
            print("  Si lavora UNA postazione alla volta: chiuderlo lì, poi riaprire qui.")
            print("  (Se sei certo che non sia aperto da nessuna parte, elimina il file")
            print(f"   {lucchetto} e riprova.)")
            print("=" * 62)
            server.server_close()
            return
    try:
        lucchetto.write_text(f"{postazione} dalle {time.strftime('%H:%M del %d/%m/%Y')}", encoding="utf-8")
    except OSError:
        pass

    def _batticuore():
        while True:
            time.sleep(60)
            try:
                lucchetto.touch()
            except OSError:
                pass

    threading.Thread(target=_batticuore, daemon=True).start()

    print("=" * 62)
    print(f"  Dashboard attiva su {indirizzo}  (in uso da: {postazione})")
    if rete:
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            print(f"  Dagli altri PC dell'ufficio: http://{ip}:{porta}")
        except Exception:
            print("  Modalità rete attiva: raggiungibile dagli altri PC su questo indirizzo IP.")
    print("  NON CHIUDERE questa finestra: tiene accesa la dashboard.")
    print("  Se chiudi il browser per sbaglio, riapri quell'indirizzo")
    print("  o rifai doppio click sull'icona di avvio.")
    print("=" * 62)
    if apri_browser:
        import webbrowser
        threading.Timer(0.5, lambda: webbrowser.open(indirizzo)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard fermata.")
    finally:
        try:
            lucchetto.unlink(missing_ok=True)
        except OSError:
            pass
