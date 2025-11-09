import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# Groq client for Whisper
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def transcribe_audio(filepath: str):
    """
    Transcribes audio using Groq Whisper API.
    """
    try:
        with open(filepath, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(os.path.basename(filepath), file.read()),
                model="whisper-large-v3",
                response_format="json",
                temperature=0.0
            )
        return transcription.text
    except Exception as e:
        return f"Error transcribing audio: {str(e)}"
