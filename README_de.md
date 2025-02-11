[![CI](https://github.com/pamagister/Photo-Composition-Designer/actions/workflows/main.yml/badge.svg)](https://github.com/pamagister/Photo-Composition-Designer/actions/workflows/main.yml)
# 📖 Photo-Composition-Designer – Dokumentation

![Photo-Composition-Designer Logo](res/images/logo.png)

Photo-Composition-Designer ist ein Tool zur automatischen Generierung von Fotokalendern aus Bildern mit Metadaten wie Datum, Standort und Beschreibung.

## 🚀 Features

✅ Automatische Bildanalyse (EXIF-Daten)  
✅ Kalender mit Feiertagen basierend auf dem Standort  
✅ Unterstützung für mehrere Bildformate  
✅ Anpassbare Layouts und Farben  
✅ Mehrsprachige Oberfläche  
✅ Interaktive GUI zur Konfiguration  
✅ Ausgabe als hochauflösende JPG-Dateien  

## 🗂️ Projektstruktur

```plaintext
📂 Photo-Composition-Designer/
 ├── 📂 res/                 # Ressourcen (Icons, Beispielbilder)
 ├── 📂 config/              # Konfigurationsdateien
 ├── 📂 src/                 # Quellcode
 ├── 📜 config.ini           # Hauptkonfigurationsdatei
 ├── 📜 anniversaries.ini    # Geburtstage und Jahrestage
 ├── 📜 locations.ini        # Standorte für die Kartenanzeige
 ├── 📜 README_DE.md         # Diese Dokumentation
 ├── 📜 README_EN.md         # Englische Dokumentation
```

## 🖼️ Workflow – Bilder organisieren

1. 📂 **Bilder in Ordner legen**  
   Die Bilder sollten in einem strukturierten Ordner (z. B. `images/`) gespeichert werden.  
2. 🔍 **EXIF-Daten überprüfen**  
   Das Tool liest Datum, Standort und Beschreibung automatisch.  
3. 🛠 **Konfiguration anpassen**  
   In der `config.ini` können Größe, Farben, Layout und mehr angepasst werden.  
4. ▶ **Generator starten**  
   Der Kalender wird erstellt und in `output/` gespeichert.

## ⚙️ GUI-Tool zur Konfiguration

![GUI](res/images/gui.png)

Das GUI-Tool ermöglicht eine komfortable Konfiguration des Kalenders.  

### 🔧 **Funktionen der GUI:**
- ✅ **Einstellungen bearbeiten**: Direktes Bearbeiten der `config.ini`.  
- 📅 **Startdatum auswählen**: Dropdown-Menüs für Tag, Monat, Jahr.  
- 📁 **Dateien auswählen**: `anniversaries.ini` und `locations.ini` per File-Dialog.  
- 🔘 **Checkboxen für Booleans**: Optionen wie `usePhotoLocationMaps`.  
- 💾 **Speichern & Generieren**: Änderungen speichern und Kalender generieren.  

## 🛠 Installation & Nutzung

### 📌 **Voraussetzungen**
- Python 3.x  
- Abhängigkeiten aus `requirements.txt`

### ⬇ **Installation**
```sh
pip install -r requirements.txt
```

### ▶ **Start des Programms**
```sh
python main.py
```

## ⚙ **Konfigurationsdateien (`config.ini`)**

Die `config.ini` enthält alle wichtigen Einstellungen.  
Kommentare hinter `;` werden im GUI-Tool als Tooltip angezeigt.

### **Beispiel:**
```ini
[SIZE]
width = 210                      ; Breite der Collage in mm
height = 148                     ; Höhe der Collage in mm
calendarHeight = 25              ; Höhe des Kalenderbereichs in mm
mapWidth = 25                    ; Breite der Standortkarte in mm
mapHeight = 25                   ; Höhe der Standortkarte in mm
dpi = 300                        ; Auflösung des Bildes in DPI
jpgQuality = 80                  ; JPG-Kompressionsqualität (1-100)

[GENERAL]
photoDirectory = ../images       ; Verzeichnis der Bilder
anniversariesConfig = anniversaries.ini  ; Datei für Jahrestage
locationsConfig = locations.ini          ; Datei für Standortdaten
```

### 🔄 **Verwendete Konfigurationsdateien**
- `anniversaries.ini` → Enthält Geburtstage und Jahrestage.  
- `locations.ini` → Enthält Standorte für Karten.  
- `config.ini` → Enthält die allgemeinen Einstellungen.

## 📜 Lizenz

MIT-Lizenz – Open Source und frei verwendbar.

---
```

---

### 📥 **Download-Option**  
Falls du die Datei direkt herunterladen möchtest, speichere den obigen Inhalt als `README_DE.md`.  
Alternativ kannst du folgende Schritte ausführen:  

**In der Konsole (Linux/macOS):**  
```sh
echo "# 📅 Photo-Composition-Designer – Dokumentation ..." > README_DE.md
```
