
FotoManager – Suite completa per la gestione delle foto
═════════════════════════════════════════════════════════════
Tab esistenti:
  1. Visualizza & Organizza  – sfoglia foto, tieni/elimina, navigazione ricorsiva
  2. Duplicati               – scansione perceptual-hash, anteprima side-by-side
  3. Riordina per Data       – sposta/copia in Anno/Mese via EXIF o mtime
  4. Separa File             – separa foto/video dai JSON (Google Takeout)
  5. Confronto Cartelle      – trova duplicati tra due cartelle
  6. Estrai Video            – crea cartella VIDEO per directory

Nuove funzionalità:
  7.  Rinomina Batch         – pattern personalizzato con data EXIF/mtime + sequenza
  8.  Recupera EXIF          – stima data da nome file e la scrive nei metadati
  9.  Dashboard              – grafici distribuzione anno/mese, fotocamera, dimensione
  10. Mappa GPS              – visualizza coordinate EXIF su mappa HTML (browser)
  11. Simili a Foto          – trova immagini simili a una foto di riferimento
  12. Qualità Foto           – sfocate/mosse, burst identici, sottoesposte/sovraesposte

Miglioramenti tab Visualizza:
  - Zoom & Pan (scroll = zoom, drag = pan)
  - Confronto affiancato
  - Filtri (anno, dimensione min/max)

Dipendenze:
    pip install Pillow imagehash send2trash numpy
    pip install piexif      (opzionale, per scrittura EXIF)
