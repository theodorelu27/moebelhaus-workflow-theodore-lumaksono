# Technische Dokumentation — Möbelhaus Kundenkontakt-Analyse

---

## 1. Datenmodell

### Schema

```sql
CREATE TABLE IF NOT EXISTS customer_contacts (
  id              SERIAL PRIMARY KEY,
  channel         VARCHAR(20) NOT NULL,
  contact_name    VARCHAR(255),
  content         TEXT,
  summary         TEXT,
  sentiment       VARCHAR(20),
  has_todo        BOOLEAN DEFAULT false,
  is_critical     BOOLEAN DEFAULT false,
  received_at     TIMESTAMPTZ,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  raw             JSONB
);
```

### Feldbeschreibungen

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `id` | SERIAL | Automatisch inkrementierter Primärschlüssel |
| `channel` | VARCHAR(20) | Eingangskanal: `webhook`, `email` oder `audio` |
| `contact_name` | VARCHAR(255) | Kundenname, extrahiert aus dem Payload, E-Mail-Header oder Transkription |
| `content` | TEXT | Vollständiger Rohtext des Kontakts |
| `summary` | TEXT | KI-generierte Zusammenfassung in 2–3 Sätzen |
| `sentiment` | VARCHAR(20) | Eines von: `gut`, `normal`, `schlecht` |
| `has_todo` | BOOLEAN | True, wenn eine Nachverfolgung oder ein Rückruf erforderlich ist |
| `is_critical` | BOOLEAN | True, wenn der Kontakt dringend oder sehr verärgert ist |
| `received_at` | TIMESTAMPTZ | Zeitstempel des Eingangs aus dem Payload |
| `created_at` | TIMESTAMPTZ | Zeitstempel der Datenbankeinspielung |
| `raw` | JSONB | Vollständiger Original-Payload für Nachvollziehbarkeit und Nachverarbeitung |

### Begründung der Designentscheidungen

**Warum eine einzelne flache Tabelle?**
Das Möbelhaus verarbeitet täglich 40–60 Kontakte über drei Kanäle. Eine einzige normalisierte Tabelle hält Abfragen einfach, vermeidet Joins bei den häufigsten Operationen und lässt sich bei Bedarf leicht erweitern. Separate Tabellen pro Kanal würden Daten fragmentieren, die dieselben analytischen Attribute teilen.

**Warum `sentiment` als VARCHAR und nicht als ENUM?**
VARCHAR ermöglicht es dem Workflow, die Ausgabe von Mistral direkt zu speichern, ohne eine Datenbankmigration durchführen zu müssen, falls sich die Sentiment-Kategorien ändern. Ein ENUM würde bei jeder Erweiterung ein ALTER TABLE erfordern.

**Warum `has_todo` und `is_critical` als separate Boolean-Felder?**
Diese Felder beantworten zwei unterschiedliche Geschäftsfragen. `has_todo` steuert Nachverfolgungs-Warteschlangen. `is_critical` löst Echtzeit-Benachrichtigungen aus. Beide Informationen in einem einzigen Schweregrad-Feld zusammenzufassen würde diese wichtige Unterscheidung verlieren.

**Warum `received_at` und `created_at` als separate Felder?**
`received_at` gibt an, wann der Kunde Kontakt aufgenommen hat. `created_at` gibt an, wann der Datensatz in die Datenbank eingetragen wurde. Die Differenz zwischen beiden kann Verarbeitungsverzögerungen aufzeigen, was für die SLA-Überwachung nützlich ist.

**Warum JSONB für `raw`?**
JSONB ermöglicht die vollständige Indizierung und Abfrage des Original-Payloads, ohne ein starres Schema für jeden Kanal definieren zu müssen. Es ermöglicht außerdem eine Nachverarbeitung — falls die KI-Analyse erneut ausgeführt werden muss, stehen die Originaldaten jederzeit zur Verfügung.

**Hinweis zur Datenbankwahl:**
PostgreSQL wurde gegenüber der internen n8n-SQLite-Datenbank gewählt, da es robuster, besser abfragbar und produktionsreif ist. Die Anbindung erfolgt über einen dedizierten Postgres-Node in n8n.

---

## 2. Modellauswahl und Begründung

### Whisper (OpenAI) — Audio-Transkription

**Verwendetes Modell:** `whisper-base`
**Bereitgestellt über:** Intern im Pyannote-Mikrodienst (`pyannote-service`)
**Einsatzbereich:** Transkription von Audiosegmenten innerhalb der Diarisierungs-Pipeline

**Warum Whisper?**
Whisper ist das leistungsfähigste verfügbare Open-Source-Transkriptionsmodell. Es unterstützt 99 Sprachen einschließlich Deutsch nativ, verarbeitet Akzente und Hintergrundgeräusche gut und ist unter der MIT-Lizenz veröffentlicht — somit vollständig selbst hostbar ohne Lizenzkosten.

**Warum das `base`-Modell?**
Das Base-Modell (74 Mio. Parameter) bietet für diesen Anwendungsfall eine gute Balance zwischen Genauigkeit und Geschwindigkeit. Ein Kundenservice-Gespräch ist in der Regel klares Audio mit wenigen Sprechern, was die größeren `medium`- oder `large`-Modelle nicht erfordert. Das Base-Modell transkribiert einen 60-sekündigen Anruf in ca. 5–10 Sekunden auf der CPU.

**Spracherkennung:** Whisper erkennt die Sprache automatisch — es wird kein fester Sprachparameter gesetzt. Das ist eine bewusste Entscheidung, da das Möbelhaus Anrufe sowohl auf Deutsch als auch auf Englisch erhalten kann. Falls ausschließlich deutsche Audiodateien verarbeitet werden sollen, kann `language="de"` in `main.py` ergänzt werden, um die Verarbeitungszeit leicht zu reduzieren.

**Kompromiss:** Das `large`-Modell ist bei stark akzentierter Sprache oder lauter Umgebung deutlich genauer. Falls die Transkriptionsqualität in der Produktion zum Problem wird, ist der Wechsel zu `whisper-large-v3` eine einfache Konfigurationsänderung in `main.py`.

**Hinweis:** Whisper läuft nicht als eigenständiger Docker-Dienst, sondern wird direkt im Pyannote-Container ausgeführt. Ein separater Whisper-Container ist nicht erforderlich.

**Lizenz:** MIT — vollständig Open Source, selbst hostbar

---

### Mistral 7B (über Ollama) — Analyse, Zusammenfassung, Sentiment

**Verwendetes Modell:** `mistral` (Mistral 7B Instruct v0.2)
**Bereitgestellt über:** `ollama/ollama`
**Einsatzbereich:** Zusammenfassung, Sentiment-Klassifikation, Todo-Erkennung für alle Kanäle

**Warum Mistral 7B?**
Mistral 7B übertrifft seine Modellgröße bei der Ausführung von Anweisungen deutlich. Für strukturierte JSON-Ausgaben ist es zuverlässig, schnell auf Consumer-Hardware und verarbeitet sowohl deutsche als auch englische Eingaben ohne zusätzliche Konfiguration.

Im Vergleich zu Alternativen:
- **Llama 3 8B** — ähnliche Qualität, etwas größer, ebenfalls eine gute Wahl
- **Phi-3 Mini** — schneller, aber weniger zuverlässig bei strukturierter JSON-Ausgabe
- **GPT-4 über API** — deutlich bessere Qualität, aber nicht selbst hostbar und verursacht laufende Tokenkosten

**Warum ein einzelnes Modell für alle Textanalysen?**
Zusammenfassung, Sentiment-Klassifikation und Todo-Erkennung werden in einem einzigen Mistral-Aufruf durchgeführt. Das reduziert die Latenz, vereinfacht den Workflow und hält den Prompt-Kontext einheitlich.

**Lizenz:** Apache 2.0 — vollständig Open Source, selbst hostbar

---

### Pyannote 3.1 — Sprecher-Diarisierung und Transkription für Audioanrufe

**Verwendetes Modell:** `pyannote/speaker-diarization-3.1`
**Bereitgestellt über:** Eigener FastAPI-Mikrodienst (`pyannote-service`)
**Einsatzbereich:** Verarbeitung von Audiodateien mit mehreren Sprechern

Siehe Abschnitt 4 für die vollständige technische Erläuterung.

**Lizenz:** MIT (HuggingFace-Token für den Modellzugriff erforderlich)

---

## 3. Kostenanalyse

### Annahmen

- Selbst gehostet auf einem dedizierten Server oder einer Cloud-VM
- Keine variablen Kosten pro Anfrage für Modelle (alle selbst gehostet)
- Kosten beziehen sich ausschließlich auf die Infrastruktur

### Kosten pro Anfrage

| Komponente | Kosten pro Anfrage |
|------------|-------------------|
| Pyannote-Diarisierung + Transkription (nur Audio) | ~€0,00 (selbst gehostet) |
| Mistral-Analyse | ~€0,00 (selbst gehostet) |
| PostgreSQL-Speicherung | ~€0,00 (vernachlässigbar) |
| **Infrastrukturkosten pro Anfrage** | **~€0,00 variabel** |

Alle variablen Kosten sind null, da jedes Modell lokal ausgeführt wird.

---

### Infrastrukturkosten nach Szenarien

#### Szenario A — Entwicklung / Kleinstbetrieb (aktuelle Einrichtung)

| Ressource | Spezifikation | Monatliche Kosten |
|-----------|---------------|-------------------|
| VPS (z. B. Hetzner CX31) | 4 vCPU, 8 GB RAM | ~€10–15 |
| Speicher | 80 GB SSD | inklusive |
| **Gesamt** | | **~€10–15/Monat** |

#### Szenario B — 1.000 Anfragen/Monat

| Kostenposition | Monatlich |
|----------------|-----------|
| Infrastruktur | €10–15 |
| Variable Modellkosten | €0 |
| **Gesamt** | **€10–15/Monat** |
| **Kosten pro Anfrage** | **~€0,01–0,015** |

#### Szenario C — 10.000 Anfragen/Monat

| Ressource | Spezifikation | Monatliche Kosten |
|-----------|---------------|-------------------|
| VPS mit GPU (z. B. Hetzner GX2-8) | 8 vCPU, 32 GB RAM, 1x GPU | ~€80–120 |
| Speicher | 160 GB SSD | inklusive |
| **Gesamt** | **~€80–120/Monat** |
| **Kosten pro Anfrage** | **~€0,008–0,012** |

Hinweis: Ab 10.000 Anfragen pro Monat lohnt sich der Einsatz einer GPU. Die Mistral-7B-Inferenz auf der CPU dauert 10–30 Sekunden pro Anfrage. Auf einer mittleren GPU reduziert sich dies auf 1–3 Sekunden.

---

### Vergleich: Selbst gehostet vs. API-basiert

| Ansatz | 1.000 Anf./Monat | 10.000 Anf./Monat |
|--------|-----------------|-------------------|
| Selbst gehostet (diese Lösung) | ~€12 | ~€100 |
| OpenAI GPT-4o + Whisper API | ~€15–25 | ~€150–250 |
| OpenAI GPT-3.5 + Whisper API | ~€5–8 | ~€50–80 |

Die selbst gehostete Lösung wird bei steigendem Volumen kosteneffizienter. Für ein Möbelhaus mit vorhersehbarem Volumen und Datenschutzanforderungen — Kundengespräche sollten das Unternehmen nicht verlassen — ist die selbst gehostete Lösung die stärkere Wahl.

---

## 4. Sprecher-Diarisierung — Umsetzung und Erläuterung

Die Diarisierung ist als eigenständiger Python-Mikrodienst umgesetzt, der neben den anderen Docker-Diensten läuft. Der Dienst ist unter `http://pyannote:8001` erreichbar und wird direkt vom n8n-Audio-Trigger angesprochen.

**Technischer Stack:**
- `pyannote/speaker-diarization-3.1` — Diarisierungsmodell
- `openai-whisper` (base) — Transkription der einzelnen Segmente
- `FastAPI` + `uvicorn` — HTTP-Schnittstelle für n8n

**Quellcode des Dienstes (`main.py`):**

```python
from fastapi import FastAPI, UploadFile, File
from pyannote.audio import Pipeline
from huggingface_hub import login
import whisper
import torch
import tempfile
import os

app = FastAPI()

HF_TOKEN = os.environ.get("HF_TOKEN")
if HF_TOKEN:
    login(token=HF_TOKEN)

diarization_pipeline = Pipeline.from_pretrained(
    "pyannote/speaker-diarization-3.1"
)
whisper_model = whisper.load_model("base")

@app.post("/diarize")
async def diarize(audio_file: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp.write(await audio_file.read())
        tmp_path = tmp.name

    try:
        diarization = diarization_pipeline(tmp_path, num_speakers=2)
        transcription = whisper_model.transcribe(tmp_path)
        segments = transcription.get("segments", [])

        speakers = {"SPEAKER_00": [], "SPEAKER_01": []}

        for segment in segments:
            best_speaker = "SPEAKER_00"
            best_overlap = 0
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                overlap = min(turn.end, segment["end"]) - max(turn.start, segment["start"])
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_speaker = speaker
            if segment["text"].strip():
                speakers[best_speaker].append(segment["text"].strip())

        return {
            "speaker_00": " ".join(speakers["SPEAKER_00"]),
            "speaker_01": " ".join(speakers["SPEAKER_01"]),
            "customer_text": " ".join(speakers["SPEAKER_00"]),
            "full_text": transcription.get("text", "")
        }
    finally:
        os.unlink(tmp_path)
```

---

### Ablauf im n8n-Workflow

```
Audio-Upload (Webhook)
        ↓
Pyannote-Dienst (/diarize)
  → Diarisierung: wer spricht wann
  → Transkription: was wird gesagt
  → Rückgabe: speaker_00, speaker_01, customer_text
        ↓
Flag Audio Source (Code-Node)
  → Markiert den Kanal als "audio"
  → Leitet customer_text weiter
        ↓
Normalizer
  → Extrahiert Namen aus der Transkription
  → Erstellt einheitliches Datenpmodell
        ↓
Ollama (Mistral)
  → Analysiert nur customer_text
  → Gibt summary, sentiment, has_todo, is_critical zurück
```

---

### Testergebnis

Testaufruf mit einer einsprachigen Audiodatei:

```json
{
  "speaker_00": "Hello, my name is Peter Hoffman. I am calling about my sofa which was delivered last week. One leg is broken and I urgently need a replacement or a callback.",
  "speaker_01": "",
  "customer_text": "Hello, my name is Peter Hoffman. I am calling about my sofa...",
  "full_text": "Hello, my name is Peter Hoffman..."
}
```

Datenbankresultat nach vollständiger Pipeline:

```
channel: audio | contact_name: Peter Hoffman | sentiment: schlecht | is_critical: true | has_todo: true
```

---

### Einschränkungen

- **Sprecheridentifikation** ist nicht möglich — Pyannote kennzeichnet Sprecher als SPEAKER_00 und SPEAKER_01. Die Annahme, dass SPEAKER_00 der Kunde ist, basiert auf der Heuristik, dass der Kunde in der Regel zuerst spricht.
- **Genauigkeit** nimmt bei mehr als 4 Sprechern, stark überlappender Sprache oder sehr kurzen Segmenten ab.
- **CPU-Inferenz** dauert ca. das 0,5-fache der Echtzeit. Eine GPU würde dies auf ca. das 0,1-fache reduzieren.
- **Erster Start** lädt ca. 1,5 GB Modellgewichte von HuggingFace herunter. Nachfolgende Starts verwenden den lokalen Cache.

---

### Einrichtung

Der Pyannote-Dienst benötigt einen HuggingFace-Token sowie die Annahme der Nutzungsbedingungen für folgende Modelle:

- `huggingface.co/pyannote/speaker-diarization-3.1`
- `huggingface.co/pyannote/segmentation-3.0`

Der Token wird als Umgebungsvariable `HF_TOKEN` in der `docker-compose.yml` hinterlegt.
