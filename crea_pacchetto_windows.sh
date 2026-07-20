#!/bin/bash
# Costruisce il pacchetto portabile per Windows (PC di Cristina).
#
# Struttura prodotta:
#   GestioneRevisioni/
#     app/        <- il programma (SOSTITUIBILE negli aggiornamenti)
#     python/     <- Python incorporato, nessuna installazione richiesta
#     dati/       <- database + testi SMS (MAI toccato dagli aggiornamenti)
#     liste/      <- excel e csv generati
#     import/     <- dove depositare i file mensili da importare
#     Avvia Revisioni.bat / Importa immatricolazioni.bat
#
# Uso:  ./crea_pacchetto_windows.sh [--con-dati]
#   --con-dati  include una copia del database attuale (primo invio)
set -euo pipefail
cd "$(dirname "$0")"

PYVER=3.12.8
BUILD=build/GestioneRevisioni
rm -rf build
mkdir -p "$BUILD"/{app,python,dati,liste,import}

echo "— Scarico Python embeddable $PYVER per Windows x64…"
curl -sL -o build/python-embed.zip "https://www.python.org/ftp/python/$PYVER/python-$PYVER-embed-amd64.zip"
unzip -q build/python-embed.zip -d "$BUILD/python"

# sys.path dell'embedded: runtime, site-packages e la cartella app
cat > "$BUILD/python/python312._pth" << 'EOF'
python312.zip
.
Lib/site-packages
../app
EOF

echo "— Installo le librerie (pure-Python, compatibili Windows)…"
python3 -m pip install --quiet --target "$BUILD/python/Lib/site-packages" openpyxl xlrd

echo "— Controllo di integrità della dashboard…"
python3 - << 'EOF'
import re, sys
sys.path.insert(0, 'app')
from revisioni.web import PAGINA
js = re.search(r'<script>(.*)</script>', PAGINA, re.S).group(1)
open('/tmp/_verifica_pagina.js', 'w').write(js)
EOF
if command -v node > /dev/null; then
    node --check /tmp/_verifica_pagina.js || { echo "ERRORE: JavaScript della dashboard rotto, pacchetto NON creato."; exit 1; }
    echo "  JavaScript ok"
fi

echo "— Copio il programma…"
cp -R app/revisioni "$BUILD/app/revisioni"
cp app/README.md "$BUILD/app/README.md" 2>/dev/null || true
find "$BUILD/app" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

if [[ "${1:-}" == "--con-dati" ]]; then
    echo "— Includo il database attuale (primo invio)…"
    cp dati/revisioni.db "$BUILD/dati/revisioni.db"
    cp dati/sms_testo*.txt "$BUILD/dati/" 2>/dev/null || true
fi

cat > "$BUILD/Avvia Revisioni.bat" << 'EOF'
@echo off
pushd "%~dp0"
title Gestione Revisioni
echo Avvio Gestione Revisioni... la dashboard si apre nel browser.
python\python.exe -m revisioni web
popd
pause
EOF

cat > "$BUILD/Importa immatricolazioni.bat" << 'EOF'
@echo off
pushd "%~dp0"
title Import immatricolazioni
echo Importo i file dalla cartella "import"...
python\python.exe -m revisioni importa-immatricolazioni import
popd
echo.
echo Finito. Puoi chiudere questa finestra.
pause
EOF

cat > "$BUILD/LEGGIMI.txt" << 'EOF'
GESTIONE REVISIONI — pacchetto portabile
========================================
Avvio:        doppio click su "Avvia Revisioni.bat" (la dashboard si apre nel browser).
Import mese:  copia il file immatricolazioni del mese nella cartella "import",
              poi doppio click su "Importa immatricolazioni.bat".

I TUOI DATI stanno nella cartella "dati" (database) e "liste" (excel generati):
NON cancellarle e includile nei backup.

USO DALLA CARTELLA CONDIVISA: si lavora UNA POSTAZIONE ALLA VOLTA.
Il programma lo controlla da solo: se e' gia' aperto altrove, avvisa e non parte.
Se resta bloccato dopo un crash, eliminare il file dati\in_uso.lock.
Il primo avvio dalla rete puo' richiedere qualche secondo in piu'.

BACKUP: a ogni avvio viene salvata una copia del database in dati\backup
(una al giorno, tiene le ultime 30).

AGGIORNAMENTI del programma: sostituire SOLO la cartella "app" con quella nuova.
I dati non vengono toccati e si adeguano da soli al primo avvio.
EOF

VERSIONE=$(date +%Y%m%d)
echo "$VERSIONE" > "$BUILD/app/VERSIONE.txt"

echo "— Creo gli archivi…"
(cd build && zip -qr "GestioneRevisioni_win64_$VERSIONE.zip" GestioneRevisioni)
(cd "$BUILD" && zip -qr "../aggiornamento_app_$VERSIONE.zip" app)

echo ""
echo "Pacchetto completo:  build/GestioneRevisioni_win64_$VERSIONE.zip  (primo invio)"
echo "Solo aggiornamento:  build/aggiornamento_app_$VERSIONE.zip       (sostituisce la cartella app)"
