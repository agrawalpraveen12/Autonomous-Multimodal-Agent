# Verification Test Cases

## 1. Audio Lecture Transcription & Summary
- **Input**: Upload an audio file (MP3/WAV, ~5 mins).
- **Prompt**: "Summarize this lecture."
- **Expected Output**:
    - **Extraction**: Shows the transcribed text.
    - **Result**:
        - 1-line summary.
        - 3 bullet points.
        - 5-sentence summary.
        - (Optional) Duration mention if supported by tool, otherwise generic summary.

## 2. PDF Meeting Notes Action Items
- **Input**: Upload a PDF with meeting notes logic.
- **Prompt**: "What are the action items?"
- **Expected Output**:
    - **Extraction**: Shows text from PDF.
    - **Result**: A list of specific action items extracted from the context.

## 3. Image Code Explanation
- **Input**: Upload a screenshot (JPG/PNG) of code.
- **Prompt**: "Explain this."
- **Expected Output**:
    - **Extraction**: Shows the OCR'd code.
    - **Result**:
        - Explanation of functionality.
        - Time complexity analysis.
        - Bug detection (if any).

## 4. YouTube Transcript
- **Input**: Text message: "Summarize this video https://www.youtube.com/watch?v=..."
- **Expected Output**:
    - **Extraction**: Fetches transcript from YouTube.
    - **Result**: Summary of the video content.

## 5. Ambiguity Handling
- **Input**: Upload a file (or just text) with NO instruction. e.g. "Here."
- **Expected Behavior**: Agent asks: "Could you clarify what you want me to do with this?" (Summarize, Translate, etc.)
