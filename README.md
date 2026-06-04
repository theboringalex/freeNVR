# freeNVR

**freeNVR** ist ein vollständig lizenzfreies, lokales NVR-System (Network Video Recorder) als Open-Source-Alternative zu Scrypted NVR. Aufnahmen bleiben ausschließlich lokal — keine Cloud, keine Abonnements.

[![HACS Custom Repository](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## Features

| Feature | Details |
|---|---|
| 📹 Kontinuierliche Aufnahme | 24/7 segmentierte MP4-Aufnahme via FFmpeg |
| 🎯 Bewegungserkennung | FFmpeg Scene-Change oder Coral TPU / TFLite KI |
| 📡 ONVIF | Kamera-Discovery, Ereignisse (Reolink, Hikvision, Dahua…) |
| 📺 HLS Live-Stream | HTTP Live Streaming für Browser & Home Assistant |
| 🤖 Google Coral TPU | Edge-TPU Objekterkennung (Person, Auto, Tier, …) |
| 🏠 Home Assistant | Custom Component via HACS — Camera, Sensor, Binary Sensor |
| 🌐 Web-UI | Darkmode-UI für Live, Aufnahmen & Verwaltung |
| 💾 Lokaler Speicher | Aufnahmen im lokalen Dateisystem, kein Cloud-Zwang |
| 🐳 Docker | Ein-Befehl-Deployment |

---

## Inhaltsverzeichnis

1. [freeNVR Server installieren](#1-freenvr-server-installieren)
2. [Home Assistant Integration via HACS](#2-home-assistant-integration-via-hacs)
3. [Kameras einrichten](#3-kameras-einrichten)
4. [ONVIF-Kameras (Reolink & Co.)](#4-onvif-kameras-reolink--co)
5. [Google Coral TPU](#5-google-coral-tpu)
6. [Home Assistant Lovelace](#6-home-assistant-lovelace)
7. [REST API Referenz](#7-rest-api-referenz)
8. [Konfiguration](#8-konfiguration-umgebungsvariablen)

---

## 1. freeNVR Server installieren

### Voraussetzungen

- Docker + Docker Compose (empfohlen)
- **oder** Python 3.11+ mit FFmpeg
- Netzwerkzugriff zu deinen Kameras

### Docker Compose (empfohlen)

```bash
# Repository klonen
git clone https://github.com/theboringalex/freenvr.git
cd freenvr

# API-Key setzen (in docker-compose.yml oder als Umgebungsvariable)
# FREENVR_API_KEY=mein-sicherer-key

# Starten
docker compose up -d

# Logs prüfen
docker compose logs -f

# Web-UI öffnen
open http://localhost:8765
```

Der Server ist bereit, wenn die Logs `freeNVR started` zeigen.

### Direkt mit Python

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8765
```

---

## 2. Home Assistant Integration via HACS

### Schritt 1: HACS installieren (falls noch nicht vorhanden)

Falls HACS noch nicht installiert ist:
→ [HACS Installationsanleitung](https://hacs.xyz/docs/setup/download)

### Schritt 2: freeNVR als Custom Repository hinzufügen

1. In Home Assistant öffne **HACS** in der Seitenleiste
2. Klicke oben rechts auf die **drei Punkte** (⋮)
3. Wähle **„Benutzerdefinierte Repositories"**

   ![HACS Custom Repos](https://raw.githubusercontent.com/theboringalex/freeNVR/main/docs/hacs_custom_repo.png)

4. Füge folgendes ein:
   - **Repository:** `https://github.com/theboringalex/freenvr`
   - **Kategorie:** `Integration`
5. Klicke **„Hinzufügen"**

### Schritt 3: Integration installieren

1. Gehe in HACS zu **Integrationen**
2. Suche nach **„freeNVR"**
3. Klicke auf **„Herunterladen"** → Bestätigen
4. **Home Assistant neu starten**

   ```
   Einstellungen → System → Neu starten
   ```

### Schritt 4: Integration konfigurieren

1. Gehe zu **Einstellungen → Geräte & Dienste**
2. Klicke **„+ Integration hinzufügen"**
3. Suche nach **„freeNVR"**
4. Fülle das Formular aus:

   | Feld | Wert | Beispiel |
   |---|---|---|
   | Host | IP-Adresse des freeNVR-Servers | `192.168.1.100` |
   | Port | Server-Port | `8765` |
   | API-Schlüssel | Wert aus `FREENVR_API_KEY` | `mein-sicherer-key` |

5. Klicke **„Senden"** — die Verbindung wird automatisch geprüft

### Schritt 5: Entities prüfen

Nach der Einrichtung erscheinen pro Kamera automatisch:

| Entity | Typ | Beschreibung |
|---|---|---|
| `camera.kamera_name` | Camera | Live-Snapshot, RTSP-Stream |
| `binary_sensor.kamera_name_bewegung` | Binary Sensor | Bewegung (1-Minuten-Fenster) |
| `sensor.freenvr_freier_speicher` | Sensor | Freier Speicherplatz in GB |
| `sensor.freenvr_aufnahmen` | Sensor | Anzahl gespeicherter Aufnahmen |

### Manuelle Installation (ohne HACS)

```bash
# Auf dem Home Assistant Host ausführen:
cp -r custom_components/freenvr /config/custom_components/freenvr

# Home Assistant neu starten, dann:
# Einstellungen → Geräte & Dienste → Integration hinzufügen → freeNVR
```

---

## 3. Kameras einrichten

### Manuell über die Web-UI

1. Öffne `http://<server-ip>:8765`
2. Gib den API-Key ein (Standard: `changeme`)
3. **Kameras → „+ Kamera hinzufügen"**
4. Ausfüllen:
   - **Name:** Beliebiger Name (z. B. „Eingang")
   - **RTSP URL:** Stream-URL der Kamera, z. B. `rtsp://192.168.1.50/h264Preview_01_main`
   - **Aufnahme:** Kontinuierlich / Nur bei Ereignis / Deaktiviert
   - **Erkennung:** FFmpeg / Coral TPU / Keine
   - **Benutzername / Passwort:** Kamera-Credentials
5. Speichern → Aufnahme startet automatisch

### Typische RTSP-URLs nach Hersteller

| Hersteller | URL-Schema |
|---|---|
| Reolink | `rtsp://user:pass@192.168.1.x/h264Preview_01_main` |
| Hikvision | `rtsp://user:pass@192.168.1.x:554/Streaming/Channels/101` |
| Dahua | `rtsp://user:pass@192.168.1.x:554/cam/realmonitor?channel=1&subtype=0` |
| Amcrest | `rtsp://user:pass@192.168.1.x:554/cam/realmonitor?channel=1&subtype=0` |
| UniFi | `rtsp://192.168.1.x:7447/<stream-key>` |
| Axis | `rtsp://user:pass@192.168.1.x/axis-media/media.amp` |
| Generic ONVIF | ONVIF Import (siehe unten) |

---

## 4. ONVIF-Kameras (Reolink & Co.)

ONVIF ermöglicht automatische Kamera-Erkennung und Bewegungsmeldungen direkt von der Kamera.

### Kamera vorbereiten (am Beispiel Reolink)

1. Reolink-App öffnen → Kamera-Einstellungen
2. **System → Netzwerk → ONVIF** aktivieren
3. Port auf **8000** setzen (Reolink-Standard)
4. **Bewegungserkennung** in den Kamera-Einstellungen aktivieren

### Import über Web-UI

1. **Kameras → „ONVIF Import"** (oranger Button)
2. Eingeben:
   - **Host:** IP-Adresse der Kamera
   - **Port:** `8000` (Reolink) oder `80` (andere)
   - **Benutzername / Passwort**
3. **„Verbindung testen"** — zeigt Gerätedaten + RTSP-URL
4. **„Importieren"** — erstellt die Kamera automatisch

### Netzwerk-Scan

1. **Kameras → „Netzwerk-Scan"** (Lupe-Button)
2. Alle ONVIF-Kameras im LAN werden automatisch gefunden (WS-Discovery)
3. Klicke **„Importieren"** bei der gewünschten Kamera

### ONVIF Bewegungsereignisse

Mit aktivierten ONVIF-Ereignissen:
- freeNVR abonniert `tns1:VideoSource/MotionAlarm` und `tns1:RuleEngine/CellMotionDetector/Motion`
- Bei Bewegungsmeldung → Ereignis in Datenbank → `binary_sensor` in HA wird `on`
- Im Modus **„Nur bei Ereignis"**: Aufnahme startet automatisch bei ONVIF-Motion

---

## 5. Google Coral TPU

KI-basierte Objekterkennung (Person, Auto, Tier, …) mit dem Google Coral Edge TPU.

### Modell herunterladen

```bash
python scripts/download_model.py
# Lädt SSD MobileNet V2 COCO (für Coral TPU + CPU-Fallback)
```

### Coral USB Accelerator

```bash
# Docker mit Coral-Gerätezugriff starten
docker compose -f docker-compose.yml -f docker-compose.coral.yml up -d
```

Das `docker-compose.coral.yml` mappt den USB-Bus ins den Container.

### Coral PCIe (M.2 / mini-PCIe)

In `docker-compose.coral.yml` den USB-Eintrag auskommentieren und `/dev/apex_0` aktivieren:
```yaml
devices:
  - /dev/apex_0:/dev/apex_0
```

### Kamera auf Coral-Erkennung umstellen

Im Kamera-Formular unter **Erkennung → „Coral TPU / TFLite (KI)"** wählen.

**Backend-Priorität (automatisch):**
1. pycoral + Edge TPU (offiziell, Python ≤ 3.9)
2. `ai-edge-litert` + `libedgetpu.so.1` (Python 3.11+, kein pycoral nötig)
3. TFLite CPU (kein Coral-Gerät)

### Erkennbare Klassen (konfigurierbar)

Standard: `person, car, truck, bus, motorcycle, dog, cat`

Anpassen via Umgebungsvariable:
```bash
CORAL_DETECT_CLASSES=person,car,dog
```

---

## 6. Home Assistant Lovelace

### Kamera-Karte

```yaml
type: picture-entity
entity: camera.eingang
camera_view: live
show_state: true
show_name: true
```

### Kamera mit Bewegungsstatus

```yaml
type: glance
entities:
  - entity: camera.eingang
  - entity: binary_sensor.eingang_bewegung
    name: Bewegung
  - entity: sensor.freenvr_freier_speicher
    name: Speicher
```

### Automation bei Bewegung

```yaml
automation:
  - alias: "freeNVR: Bewegung Eingang"
    trigger:
      - platform: state
        entity_id: binary_sensor.eingang_bewegung
        to: "on"
    action:
      - service: notify.mobile_app_iphone
        data:
          title: "Bewegung erkannt"
          message: "Eingang: Bewegung erkannt"
          data:
            entity_id: camera.eingang
```

### Dashboard mit mehreren Kameras

```yaml
type: grid
columns: 2
cards:
  - type: picture-entity
    entity: camera.eingang
    camera_view: live
  - type: picture-entity
    entity: camera.garage
    camera_view: live
  - type: history-graph
    entities:
      - entity: binary_sensor.eingang_bewegung
      - entity: binary_sensor.garage_bewegung
    hours_to_show: 24
  - type: sensor
    entity: sensor.freenvr_freier_speicher
    graph: line
```

---

## 7. REST API Referenz

Alle Endpunkte erfordern `X-API-Key: <dein-key>` als HTTP-Header.

```
# Kameras
GET    /api/cameras                    Alle Kameras
POST   /api/cameras                    Kamera hinzufügen
GET    /api/cameras/{id}               Kamera abrufen
PATCH  /api/cameras/{id}               Kamera bearbeiten
DELETE /api/cameras/{id}               Kamera löschen

# Aufnahmen
GET    /api/recordings                 Aufnahmen (Filter: camera_id, start, end)
GET    /api/recordings/{id}/download   Aufnahme herunterladen
DELETE /api/recordings/{id}            Aufnahme löschen
GET    /api/recordings/storage/info    Speicherinfos

# Streaming
GET    /api/streams/{id}/hls/start     HLS-Stream starten
GET    /api/streams/{id}/hls/stop      HLS-Stream stoppen
GET    /api/streams/{id}/hls/live.m3u8 HLS-Playlist
GET    /api/streams/{id}/snapshot      JPEG-Snapshot

# Ereignisse
GET    /api/events                     Alle Ereignisse (Filter: camera_id, event_type)
GET    /api/events/latest              Neueste Ereignisse

# ONVIF
GET    /api/onvif/discover             WS-Discovery im Netzwerk
GET    /api/onvif/probe                Kamera prüfen (Gerätedaten + RTSP-URL)
POST   /api/onvif/import               Kamera via ONVIF importieren
```

**Swagger UI:** `http://<server>:8765/docs`

---

## 8. Konfiguration (Umgebungsvariablen)

| Variable | Standard | Beschreibung |
|---|---|---|
| `FREENVR_API_KEY` | `changeme` | **Unbedingt ändern!** |
| `FREENVR_PORT` | `8765` | Server-Port |
| `RECORDINGS_PATH` | `recordings` | Pfad für Aufnahmen |
| `SEGMENT_DURATION` | `60` | Aufnahme-Segmentlänge (Sekunden) |
| `MOTION_ENABLED` | `true` | FFmpeg-Bewegungserkennung |
| `MOTION_THRESHOLD` | `0.02` | Empfindlichkeit (0.0–1.0) |
| `ONVIF_PULL_INTERVAL` | `2.0` | ONVIF-Polling-Intervall (Sekunden) |
| `CORAL_MODEL_PATH` | `models/ssd_mobilenet_v2_coco_quant_postprocess_edgetpu.tflite` | Coral-Modell |
| `CORAL_SCORE_THRESHOLD` | `0.5` | Mindest-Confidence für Erkennungen |
| `CORAL_INFERENCE_FPS` | `1.0` | Frames pro Sekunde für Inference |
| `CORAL_DETECT_CLASSES` | `person,car,truck,bus,motorcycle,dog,cat` | Zu erkennende COCO-Klassen |

---

## Unterstützte Kameras

- Alle Kameras mit **RTSP**-Stream (H.264)
- **ONVIF**-kompatible Kameras (WS-Discovery, PullPoint Events)
- Geprüft: Reolink, Hikvision, Dahua, Amcrest, UniFi, Axis

---

## Lizenz

MIT License — vollständig Open Source, keine Nutzungsgebühren, keine Abonnements.
