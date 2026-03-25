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

print("Loading diarization pipeline...")
diarization_pipeline = Pipeline.from_pretrained(
    "pyannote/speaker-diarization-3.1"
)

print("Loading Whisper model...")
whisper_model = whisper.load_model("base")

@app.post("/diarize")
async def diarize(audio_file: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        contents = await audio_file.read()
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        diarization = diarization_pipeline(tmp_path, num_speakers=2)
        full_transcription = whisper_model.transcribe(tmp_path)
        segments = full_transcription.get("segments", [])

        speakers = {"SPEAKER_00": [], "SPEAKER_01": []}

        for segment in segments:
            seg_start = segment["start"]
            seg_end = segment["end"]
            seg_text = segment["text"].strip()

            best_speaker = "SPEAKER_00"
            best_overlap = 0

            for turn, _, speaker in diarization.itertracks(yield_label=True):
                overlap = min(turn.end, seg_end) - max(turn.start, seg_start)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_speaker = speaker

            if seg_text:
                speakers[best_speaker].append(seg_text)

        speaker_00_text = " ".join(speakers.get("SPEAKER_00", []))
        speaker_01_text = " ".join(speakers.get("SPEAKER_01", []))

        return {
            "speaker_00": speaker_00_text,
            "speaker_01": speaker_01_text,
            "customer_text": speaker_00_text,
            "full_text": full_transcription.get("text", "")
        }

    finally:
        os.unlink(tmp_path)