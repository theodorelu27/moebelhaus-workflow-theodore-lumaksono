# Möbelhaus Kundenkontakt-Analyse — n8n Workflow

Ein selbst gehosteter n8n-Workflow, der Kundenkontakte aus verschiedenen Kanälen zentralisiert, mit Open-Source-KI-Modellen analysiert und kritische Fälle in Echtzeit meldet.

---

## Kontext
Dieses Projekt entstand im Rahmen eines Take-Home-Assessments. Der n8n-Workflow 
zentralisiert Kundenkontakte aus drei Kanälen (Webhook, E-Mail/IMAP und Audio) 
und verarbeitet sie mit einem vollständig lokal betriebenen KI-Stack: Pyannote 
übernimmt die Sprecher-Diarisierung und Transkription, Mistral 7B via Ollama 
analysiert die Stimmung und erkennt kritische Fälle in Echtzeit. Alle Dienste 
laufen selbst gehostet via Docker Compose – ohne externe API-Aufrufe.

## Architekturübersicht

```
Webhook ──────────────────────────────────────────┐
                                                  ▼
Audio-Upload → Pyannote → Flag Audio Source → Normalizer → Ollama-Analyse → Antwort-Parser → Kritisch-Prüfung
                                                                                                    │
E-Mail (IMAP) ────────────────────────────────────┘                                     ┌──────────┴──────────┐
                                                                                        true               false
                                                                                         │                   │
                                                                                  Benachrichtigung       Speichern
                                                                                         │
                                                                                      Speichern
```

**Hinweis zur Audio-Verarbeitung:** Der Pyannote-Dienst übernimmt sowohl die Sprecher-Diarisierung als auch die Transkription (via Whisper intern). Ein separater Whisper-Container ist nicht erforderlich.

---

## Dienste

| Dienst | Port | Zweck |
|--------|------|-------|
| n8n | 5678 | Workflow-Automatisierung |
| Pyannote | 8001 | Sprecher-Diarisierung + Transkription |
| Ollama + Mistral | 11434 | Sentiment-Analyse und Zusammenfassung |
| PostgreSQL 15 | 5432 | Kontaktspeicherung |

Für lokale E-Mail-Tests steht ein separater Greenmail-Dienst bereit (Port 3025 / 3143 / 8080). Dieser wird über `docker-compose.test.yml` gestartet und ist nicht Teil der Produktionsarchitektur.

---

## Voraussetzungen

- Docker Desktop (Windows/Mac/Linux)
- Docker Compose v2+
- Mindestens 8 GB RAM (Mistral 7B benötigt ca. 5 GB, Pyannote ca. 2 GB)
- Mindestens 15 GB freier Speicherplatz
- HuggingFace-Konto mit akzeptierten Nutzungsbedingungen für:
  - `pyannote/speaker-diarization-3.1`
  - `pyannote/segmentation-3.0`

---

## Einrichtung

### 1. Projektordner erstellen

```bash
mkdir moebelhaus
cd moebelhaus
```

### 2. Dateien anlegen

Folgende Dateien aus diesem Repository in den Ordner kopieren:
- `docker-compose.yml`
- `init.sql`
- `pyannote-service/main.py`
- `pyannote-service/Dockerfile`

### 3. HuggingFace-Token hinterlegen

In der `docker-compose.yml` den Platzhalter ersetzen:

```yaml
environment:
  - HF_TOKEN=your_huggingface_token_here
```

### 4. Alle Dienste starten

```bash
docker compose up -d
```

Beim ersten Start werden alle Images und Modelle heruntergeladen — je nach Verbindungsgeschwindigkeit kann das 15–20 Minuten dauern. Pyannote lädt beim ersten Start ca. 1,5 GB Modellgewichte herunter.

### 5. Mistral in Ollama laden

```bash
docker exec -it ollama ollama pull mistral
```

### 6. n8n öffnen

Im Browser `http://localhost:5678` aufrufen und sich anmelden:
- Benutzername: `admin`
- Passwort: `admin123` (in der Produktion ändern)

### 7. Workflow importieren

1. Auf `Add workflow` klicken
2. Drei-Punkte-Menü → `Import from file`
3. `furniture-workflow.json` auswählen
4. Workflow auf **Aktiv** schalten

### 8. Postgres-Zugangsdaten in n8n hinterlegen

1. In der linken Seitenleiste `Credentials` öffnen
2. `Add Credential` → nach `Postgres` suchen
3. Folgende Werte eintragen:
   - Host: `postgres`
   - Port: `5432`
   - Datenbank: `furnituredb`
   - Benutzer: `furniture`
   - Passwort: `furniture123`
4. `Test` klicken, dann speichern

---

## Tests

### Test 1 — Webhook (positiver Kontakt)

```powershell
$body = @{
  name = "Anna Schmidt"
  message = "Guten Tag, ich wollte mich nur bedanken. Der Tisch wurde pünktlich geliefert und die Qualität ist hervorragend."
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://localhost:5678/webhook/moebelhaus-webhook" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body
```

Erwartetes Ergebnis: `sentiment = gut`, `is_critical = false`

### Test 2 — Webhook (normaler Kontakt)

```powershell
$body = @{
  name = "Thomas Becker"
  message = "Guten Tag, ich wollte fragen wann mein Tisch geliefert wird. Die Bestellnummer ist 12345. Danke."
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://localhost:5678/webhook/moebelhaus-webhook" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body
```

Erwartetes Ergebnis: `sentiment = normal`, `is_critical = false`, `has_todo = true`

### Test 3 — Webhook (kritischer Kontakt)

```powershell
$body = @{
  name = "Hans Weber"
  message = "Das ist ein Skandal! Ich warte seit 3 Wochen auf meine Bestellung. Ich werde rechtliche Schritte einleiten!"
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://localhost:5678/webhook/moebelhaus-webhook" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body
```

Erwartetes Ergebnis: `sentiment = schlecht`, `is_critical = true`, Benachrichtigungsknoten wird ausgelöst

### Test 4 — Audio-Upload

```bash
curl.exe -X POST "http://localhost:5678/webhook/moebelhaus-audio" `
  -F "data=@/pfad/zur/audiodatei.wav"
```

Erwartetes Ergebnis: `channel = audio`, Name wird aus der Transkription extrahiert, Sentiment wird nur anhand des Kundenanteils analysiert

### Test 5 — E-Mail (mit Greenmail)

Zuerst den Greenmail-Testdienst starten:

```bash
docker compose -f docker-compose.test.yml up -d
```

Den E-Mail-Trigger in n8n auf folgende Werte setzen:
- Host: `greenmail`, Port: `3143`, Benutzer: `test@example.com`, Passwort: `password`, TLS: aus

Dann eine Test-E-Mail senden:

```powershell
$client = New-Object System.Net.Mail.SmtpClient("localhost", 3025)
$client.EnableSsl = $false
$mail = New-Object System.Net.Mail.MailMessage
$mail.From = New-Object System.Net.Mail.MailAddress("kunde@example.com", "Maria Fischer")
$mail.To.Add("test@example.com")
$mail.Subject = "Frage zur Lieferung"
$mail.Body = "Guten Tag, wann wird mein Tisch geliefert? Bestellnummer 12345. Danke."
$client.Send($mail)
```

Erwartetes Ergebnis: `channel = email`, `contact_name = Maria Fischer`

### Ergebnisse in der Datenbank prüfen

```powershell
docker exec -it postgres psql -U furniture -d furnituredb `
  -c "SELECT id, channel, contact_name, sentiment, is_critical, has_todo FROM customer_contacts ORDER BY id DESC LIMIT 5;"
```

---

## Projektstruktur

```
moebelhaus/
├── docker-compose.yml          # Produktionsdienste
├── docker-compose.test.yml     # Testdienste (Greenmail für E-Mail-Tests)
├── init.sql                    # Datenbankschema
├── furniture-workflow.json     # n8n-Workflow-Export
├── files/                      # Einhängepunkt für Audiodateien
└── pyannote-service/
    ├── Dockerfile
    ├── requirements.txt
    └── main.py                 # FastAPI-Dienst für Diarisierung
```

---

## Datenbank zurücksetzen

```powershell
docker compose down
docker volume rm moebelhaus_postgres_data
docker compose up -d
```

---

## Hinweise

- Der E-Mail-Trigger (IMAP) benötigt gültige IMAP-Zugangsdaten. Für Produktionsbetrieb die Greenmail-Zugangsdaten durch echte IMAP-Daten ersetzen.
- Whisper erkennt die Sprache der Audiodatei automatisch — es ist kein fester Sprachparameter gesetzt. Das ermöglicht die Verarbeitung sowohl deutschsprachiger als auch englischsprachiger Anrufe. Falls ausschließlich deutsche Audiodateien verarbeitet werden, kann `language="de"` in `main.py` ergänzt werden.
- Mistral-Antworten sind nicht deterministisch — die Sentiment-Ergebnisse können bei identischen Eingaben leicht variieren.
- Der HuggingFace-Token muss vor dem ersten Start in der `docker-compose.yml` hinterlegt werden. Ohne Token kann Pyannote das Modell nicht herunterladen.
