# freeNVR

**freeNVR** ist ein vollständig lizenzfreies, lokales NVR-System (Network Video Recorder) als Open-Source-Alternative zu Scrypted NVR. Aufnahmen bleiben ausschließlich lokal — keine Cloud, keine Abonnements.

## Features

| Feature | Details |
|---|---|
| 📹 Kontinuierliche Aufnahme | 24/7 segmentierte MP4-Aufnahme via FFmpeg |
| 🎯 Bewegungserkennung | FFmpeg Scene-Change-Erkennung |
| 📡 Protokolle | RTSP, ONVIF-kompatibel |
| 📺 Live-Streaming | HLS (HTTP Live Streaming) |
| 🏠 Home Assistant | Custom Component (HACS-kompatibel) |
| 🌐 Web-UI | Darkmode-UI für Live, Aufnahmen & Verwaltung |
| 🔑 API-Key Auth | Einfache REST-API-Absicherung |
| 💾 Lokaler Speicher | Aufnahmen im lokalen Dateisystem |
| 🐳 Docker | Ein-Befehl-Deployment |

## Schnellstart

### Docker Compose

```bash
# Repository klonen
git clone https://github.com/theboringalex/freenvr.git
cd freenvr

# API-Key in docker-compose.yml anpassen (FREENVR_API_KEY)

# Starten
docker compose up -d

# Web-UI öffnen
open http://localhost:8765
```

### Kamera hinzufügen

1. Web-UI öffnen: `http://localhost:8765`
2. API-Key eingeben (Standard: `changeme`)
3. "Kameras" → "+ Kamera hinzufügen"
4. RTSP-URL der Kamera eingeben, z. B. `rtsp://192.168.1.100/stream1`
5. Aufnahmemodus wählen: Kontinuierlich, Bewegung oder Deaktiviert

### Direkt mit Python

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8765
```

## Home Assistant Integration

### Methode 1: HACS (empfohlen)

1. HACS öffnen → "Integrationen" → "+ Erkunden & Herunterladen"
2. Nach "freeNVR" suchen
3. Installieren und Home Assistant neu starten

### Methode 2: Manuell

```bash
cp -r homeassistant/custom_components/freenvr \
      /config/custom_components/freenvr
```

Home Assistant neu starten, dann:

**Einstellungen → Geräte & Dienste → Integration hinzufügen → freeNVR**

Folgende Daten eingeben:
- **Host**: IP-Adresse des freeNVR-Servers
- **Port**: `8765`
- **API-Schlüssel**: Wie in `docker-compose.yml` konfiguriert

### HA-Entities pro Kamera

| Entity | Typ | Beschreibung |
|---|---|---|
| `camera.kamera_name` | Camera | Live-Snapshot, RTSP-Stream |
| `binary_sensor.kamera_name_bewegung` | Binary Sensor | Bewegungserkennung (1 Min. Fenster) |
| `sensor.freenvr_freier_speicher` | Sensor | Freier Speicherplatz in GB |
| `sensor.freenvr_aufnahmen` | Sensor | Anzahl der Aufnahmen |

### Beispiel: Lovelace-Karte

```yaml
type: picture-entity
entity: camera.eingang
camera_view: live
show_state: true
show_name: true
```

### Beispiel: Automation bei Bewegung

```yaml
automation:
  - alias: "Bewegung Eingang"
    trigger:
      - platform: state
        entity_id: binary_sensor.eingang_bewegung
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "Bewegung erkannt"
          message: "Eingang: Bewegung erkannt"
```

## REST API

Alle Endpunkte erfordern den Header `X-API-Key: <dein-key>`.

```
GET  /api/cameras              - Alle Kameras auflisten
POST /api/cameras              - Kamera hinzufügen
GET  /api/cameras/{id}         - Kamera abrufen
PATCH /api/cameras/{id}        - Kamera bearbeiten
DELETE /api/cameras/{id}       - Kamera löschen

GET  /api/recordings           - Aufnahmen auflisten (Filter: camera_id, start, end)
GET  /api/recordings/{id}/download  - Aufnahme herunterladen
DELETE /api/recordings/{id}    - Aufnahme löschen
GET  /api/recordings/storage/info   - Speicherinfos

GET  /api/streams/{id}/hls/start    - HLS-Stream starten
GET  /api/streams/{id}/hls/live.m3u8 - HLS-Playlist
GET  /api/streams/{id}/snapshot     - JPEG-Snapshot

GET  /api/events               - Ereignisse auflisten
GET  /api/events/latest        - Neueste Ereignisse
```

## Konfiguration (Umgebungsvariablen)

| Variable | Standard | Beschreibung |
|---|---|---|
| `FREENVR_API_KEY` | `changeme` | API-Schlüssel |
| `FREENVR_PORT` | `8765` | Server-Port |
| `RECORDINGS_PATH` | `recordings` | Aufnahmepfad |
| `SEGMENT_DURATION` | `60` | Segmentlänge in Sekunden |
| `MOTION_ENABLED` | `true` | Bewegungserkennung aktivieren |
| `MOTION_THRESHOLD` | `0.02` | Empfindlichkeit (0.0–1.0) |

## Unterstützte Kameras

- Alle Kameras mit **RTSP**-Stream
- **ONVIF**-kompatible Kameras
- Geprüft mit: Reolink, Hikvision, Dahua, Amcrest, UniFi, Axis

## Lizenz

MIT License — vollständig Open Source, keine Nutzungsgebühren.
