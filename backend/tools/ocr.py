"""PDF and image text extraction.

PDF: native text via pypdf, with an automatic vision-OCR fallback for scanned /
image-only PDFs. Images: Groq vision OCR. Both paths return a structured
``tool_result`` dict including an OCR confidence estimate.
"""
import os
import re
import json
import base64
from typing import Tuple

from pypdf import PdfReader
from groq import Groq
from dotenv import load_dotenv

from .util import tool_result, with_retries

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

# Cap OCR-fallback pages to keep latency and cost bounded.
MAX_OCR_PAGES = int(os.getenv("MAX_OCR_PAGES", "8"))

_OCR_PROMPT = (
    "You are an OCR engine. Transcribe ALL visible text from this image exactly. "
    "Respond ONLY with a JSON object of the form "
    '{"text": "<verbatim text>", "confidence": <0.0-1.0>} '
    "where confidence is your certainty that the transcription is complete and correct. "
    "If there is no readable text, use an empty string and confidence 0.0."
)


def encode_image(filepath: str) -> str:
    with open(filepath, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _vision_ocr(base64_image: str, mime: str = "image/jpeg") -> Tuple[str, float]:
    """Run vision OCR on a base64 image, returning (text, confidence)."""
    completion = with_retries(
        client.chat.completions.create,
        model=VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _OCR_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{base64_image}"},
                    },
                ],
            }
        ],
        temperature=0,
        max_tokens=2048,
    )
    raw = (completion.choices[0].message.content or "").strip()

    # Preferred path: model returned the requested JSON envelope.
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            data = json.loads(match.group(0))
            text = str(data.get("text", "")).strip()
            conf = float(data.get("confidence", 0.0))
            return text, max(0.0, min(1.0, conf))
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    # Fallback: treat the whole reply as text with a heuristic confidence.
    return raw, (0.6 if raw else 0.0)


def extract_text_from_image(filepath: str) -> dict:
    """Extract text from an image file using Groq vision OCR."""
    try:
        ext = os.path.splitext(filepath)[1].lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"
        text, conf = _vision_ocr(encode_image(filepath), mime)
        if not text:
            return tool_result(
                True, "", None,
                source_type="image", method="vision_ocr", confidence=0.0,
                note="No readable text detected in image.",
            )
        return tool_result(
            True, text, None,
            source_type="image", method="vision_ocr", confidence=round(conf, 2),
        )
    except Exception as exc:  # noqa: BLE001
        return tool_result(
            False, "", f"Could not read image: {exc}",
            source_type="image", method="vision_ocr", confidence=0.0,
        )


def _ocr_scanned_pdf(filepath: str) -> dict:
    """Vision-OCR fallback for scanned / image-only PDFs (requires PyMuPDF)."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return tool_result(
            False, "",
            "This PDF appears scanned (no embedded text) and the OCR fallback "
            "dependency 'pymupdf' is not installed.",
            source_type="pdf", method="ocr_fallback_unavailable", confidence=0.0,
        )

    try:
        doc = fitz.open(filepath)
        total_pages = doc.page_count
        pages_to_ocr = min(total_pages, MAX_OCR_PAGES)
        chunks, confs = [], []
        for i in range(pages_to_ocr):
            page = doc.load_page(i)
            pix = page.get_pixmap(dpi=200)
            b64 = base64.b64encode(pix.tobytes("png")).decode("utf-8")
            text, conf = _vision_ocr(b64, "image/png")
            if text:
                chunks.append(text)
                confs.append(conf)
        doc.close()

        combined = "\n\n".join(chunks).strip()
        avg_conf = round(sum(confs) / len(confs), 2) if confs else 0.0
        truncated = total_pages > pages_to_ocr
        if not combined:
            return tool_result(
                True, "", None,
                source_type="pdf", method="ocr_fallback", confidence=0.0,
                pages=total_pages, note="OCR fallback found no readable text.",
            )
        return tool_result(
            True, combined, None,
            source_type="pdf", method="ocr_fallback", confidence=avg_conf,
            pages=total_pages, ocr_pages=pages_to_ocr, truncated=truncated,
        )
    except Exception as exc:  # noqa: BLE001
        return tool_result(
            False, "", f"OCR fallback failed: {exc}",
            source_type="pdf", method="ocr_fallback", confidence=0.0,
        )


def extract_text_from_pdf(filepath: str) -> dict:
    """Extract text from a PDF: native text first, vision OCR fallback if scanned."""
    try:
        reader = PdfReader(filepath)
        text = "".join((page.extract_text() or "") + "\n" for page in reader.pages).strip()
    except Exception as exc:  # noqa: BLE001
        return tool_result(
            False, "", f"Could not read PDF: {exc}",
            source_type="pdf", method="pypdf", confidence=0.0,
        )

    # Heuristic: too little text => likely scanned => OCR fallback.
    if len(text) < 40:
        return _ocr_scanned_pdf(filepath)

    return tool_result(
        True, text, None,
        source_type="pdf", method="pypdf", confidence=0.99,
        pages=len(reader.pages),
    )
