"""YouTube transcript fetching.

Returns a structured ``tool_result`` dict so the agent graph can branch
consistently.
"""
import re
from youtube_transcript_api import YouTubeTranscriptApi

from .util import tool_result


def extract_video_id(url: str) -> str | None:
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    return match.group(1) if match else None


def get_youtube_transcript(url: str) -> dict:
    video_id = extract_video_id(url)
    if not video_id:
        return tool_result(
            False, "",
            "Could not extract a YouTube video ID from the URL. Please check the link.",
            source_type="youtube",
        )
    try:
        entries = YouTubeTranscriptApi.get_transcript(video_id)
        text = " ".join(t["text"] for t in entries)
        return tool_result(True, text, None, source_type="youtube", video_id=video_id)
    except Exception as exc:  # noqa: BLE001
        return tool_result(
            False, "",
            f"Could not fetch transcript — the video may not have captions or may be private. ({exc})",
            source_type="youtube", video_id=video_id,
        )
