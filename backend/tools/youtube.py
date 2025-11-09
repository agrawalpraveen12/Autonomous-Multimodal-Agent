from youtube_transcript_api import YouTubeTranscriptApi
import re

def extract_video_id(url: str):
    """
    Extracts video ID from various YouTube URL formats.
    """
    regex = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(regex, url)
    if match:
        return match.group(1)
    return None

def get_youtube_transcript(url: str):
    try:
        video_id = extract_video_id(url)
        if not video_id:
            return "Error: Could not extract video ID from URL."
            
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        transcript_text = " ".join([t['text'] for t in transcript_list])
        return transcript_text
    except Exception as e:
        return f"Could not fetch transcript. Video may not have captions available or may be private. Error: {str(e)}"
