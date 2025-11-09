import os
import base64
from pypdf import PdfReader
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def extract_text_from_pdf(filepath: str):
    """Extract text from PDF using PyPDF"""
    try:
        reader = PdfReader(filepath)
        text = "".join(page.extract_text() + "\n" for page in reader.pages)
        return text.strip() or "[PDF yielded no text]"
    except Exception as e:
        return f"Error extracting PDF: {str(e)}"

def encode_image(filepath: str):
    """Encode image to base64"""
    with open(filepath, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')

def extract_text_from_image(filepath: str, prompt: str = "Extract all visible text from this image."):
    """Extract text from image using Groq Vision API"""
    try:
        base64_image = encode_image(filepath)
        
        completion = client.chat.completions.create(
            model=os.getenv("GROQ_VISION_MODEL", "llama-3.2-11b-vision-preview"),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                            },
                        },
                    ],
                }
            ],
            temperature=0,
            max_tokens=1024,
        )
        
        return completion.choices[0].message.content or "[No text detected]"
        
    except Exception as e:
        return f"Error extracting text from image: {str(e)}"
