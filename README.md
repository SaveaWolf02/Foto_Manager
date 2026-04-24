# 📷 FotoManager

**Suite completa per la gestione, organizzazione e analisi delle foto.**

FotoManager è un'applicazione desktop con interfaccia a schede che offre strumenti potenti per gestire grandi librerie fotografiche: dalla pulizia dei duplicati all'estrazione dei metadati EXIF, dalla visualizzazione su mappa GPS all'analisi della qualità delle immagini.

---

## 🗂️ Funzionalità

### Schede principali

| # | Scheda | Descrizione |
|---|--------|-------------|
| 1 | **Visualizza & Organizza** | Sfoglia foto con navigazione ricorsiva nelle cartelle, tieni o elimina immagini rapidamente |
| 2 | **Duplicati** | Scansione tramite perceptual hash con anteprima affiancata per confronto visivo |
| 3 | **Riordina per Data** | Sposta o copia i file in una struttura `Anno/Mese` usando data EXIF o data di modifica |
| 4 | **Separa File** | Separa foto e video dai file JSON esportati da Google Takeout |
| 5 | **Confronto Cartelle** | Trova duplicati tra due cartelle distinte |
| 6 | **Estrai Video** | Crea automaticamente una cartella `VIDEO` per ogni directory scansionata |
| 7 | **Rinomina Batch** | Rinomina file in blocco con pattern personalizzato: data EXIF/mtime + numerazione sequenziale |
| 8 | **Recupera EXIF** | Stima la data di scatto dal nome del file e la scrive nei metadati EXIF |
| 9 | **Dashboard** | Grafici interattivi con distribuzione per anno/mese, fotocamera utilizzata e dimensione dei file |
| 10 | **Mappa GPS** | Visualizza le coordinate EXIF di tutte le foto su una mappa HTML nel browser |
| 11 | **Simili a Foto** | Trova immagini visivamente simili a una foto di riferimento scelta dall'utente |
| 12 | **Qualità Foto** | Rileva foto sfocate/mosse, burst quasi identici, immagini sottoesposte o sovraesposte |

---

### ✨ Miglioramenti alla scheda Visualizza

- **Zoom & Pan** — scroll del mouse per zoomare, trascinamento per spostarsi sull'immagine
- **Confronto affiancato** — visualizza due foto fianco a fianco per un confronto diretto
- **Filtri avanzati** — filtra per anno di scatto, dimensione minima e massima del file

---

## ⚙️ Installazione

### Requisiti

- Python 3.8+
- Le librerie elencate di seguito

### Dipendenze

Installa le dipendenze principali:

```bash
pip install Pillow imagehash send2trash numpy
```

Installa la dipendenza opzionale per la **scrittura dei metadati EXIF** (necessaria per la scheda *Recupera EXIF*):

```bash
pip install piexif
```

---

## 🚀 Avvio

```bash
python fotomanager.py
```

---

## 📁 Struttura del progetto

```
FotoManager/
├── fotomanager.py        # Entry point principale
├── tabs/
│   ├── visualizza.py     # Scheda Visualizza & Organizza
│   ├── duplicati.py      # Scheda Duplicati
│   ├── riordina.py       # Scheda Riordina per Data
│   ├── separa.py         # Scheda Separa File
│   ├── confronto.py      # Scheda Confronto Cartelle
│   ├── video.py          # Scheda Estrai Video
│   ├── rinomina.py       # Scheda Rinomina Batch
│   ├── exif.py           # Scheda Recupera EXIF
│   ├── dashboard.py      # Scheda Dashboard
│   ├── mappa.py          # Scheda Mappa GPS
│   ├── simili.py         # Scheda Simili a Foto
│   └── qualita.py        # Scheda Qualità Foto
└── README.md
```

---

## 📦 Dipendenze – Riepilogo

| Libreria | Uso | Obbligatoria |
|----------|-----|:---:|
| `Pillow` | Lettura/scrittura immagini, metadati EXIF | ✅ |
| `imagehash` | Perceptual hashing per rilevamento duplicati | ✅ |
| `send2trash` | Eliminazione sicura nel cestino di sistema | ✅ |
| `numpy` | Calcoli su array per analisi qualità | ✅ |
| `piexif` | Scrittura metadati EXIF nei file immagine | ⚪ opzionale |

---

## 📝 Note

- I file eliminati tramite l'interfaccia vengono spostati nel **cestino di sistema**, non eliminati permanentemente (grazie a `send2trash`).
- La **Mappa GPS** genera un file HTML autonomo che si apre nel browser predefinito; non richiede connessione internet se si usa un layer di mappe offline.
- La scheda **Recupera EXIF** richiede `piexif` per scrivere i metadati; senza di essa può solo stimare la data senza salvarla.
- Il **perceptual hash** usato per i duplicati è robusto a piccole differenze di compressione o ridimensionamento, ma non a modifiche sostanziali dell'immagine.

---

## 📄 Licenza

Distribuito sotto licenza MIT. Consulta il file `LICENSE` per i dettagli.
