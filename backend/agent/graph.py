"""LangGraph agent workflow — Phase 4 additions:
  - Fallback API key (4.1): invoke_llm() tries GROQ_API_KEY first, falls back to
    GROQ_API_KEY_FALLBACK on 401 / 429 / rate-limit errors. Logged in plan_log.
  - Audio → auto-summarize (4.3): when source_type=="audio" and classifier returns
    "chat" (ambiguous fallback), override intent to "summarize".
  - Conversation history (4.4): last MAX_HISTORY turns are sent to the LLM in the
    "chat" execution path so the agent can refer to earlier exchanges.

Nodes: process_input → planner → classify → [clarify | execute] → END
"""

import json
import os
import re
import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from .state import AgentState
from tools.audio import transcribe_audio
from tools.ocr import extract_text_from_image, extract_text_from_pdf
from tools.youtube import get_youtube_transcript

# ---------------------------------------------------------------------------
# LLM — primary + optional fallback (Phase 4.1)
# ---------------------------------------------------------------------------
_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

_primary_llm = ChatGroq(
    model=_MODEL,
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0,
    streaming=True,
)

_fallback_key = os.getenv("GROQ_API_KEY_FALLBACK", "").strip()
_fallback_llm = (
    ChatGroq(model=_MODEL, api_key=_fallback_key, temperature=0, streaming=True)
    if _fallback_key else None
)

MAX_CONTENT_CHARS = int(os.getenv("MAX_CONTENT_CHARS", "24000"))
MAX_HISTORY       = int(os.getenv("MAX_HISTORY_TURNS", "8"))


def _ts() -> str:
    return time.strftime("%H:%M:%S")


def invoke_llm(messages: list, plan_log: list | None = None) -> object:
    """Invoke the primary LLM; fall back to the backup key on auth/rate errors."""
    try:
        return _primary_llm.invoke(messages)
    except Exception as exc:
        err = str(exc).lower()
        is_recoverable = any(kw in err for kw in ("401", "429", "rate", "auth", "limit", "quota"))
        if _fallback_llm and is_recoverable:
            if plan_log is not None:
                plan_log.append(
                    f"[{_ts()}] ⚠ Primary API key failed ({type(exc).__name__}); "
                    "switching to fallback key."
                )
            return _fallback_llm.invoke(messages)
        raise


def _truncate(text: str, plan_log: list) -> tuple[str, list]:
    if len(text) <= MAX_CONTENT_CHARS:
        return text, plan_log
    trimmed = text[:MAX_CONTENT_CHARS]
    plan_log = plan_log + [
        f"[{_ts()}] ⚠ Content truncated to {MAX_CONTENT_CHARS} chars "
        f"(original {len(text)} chars) to stay within token limit."
    ]
    return trimmed, plan_log


# ---------------------------------------------------------------------------
# Node: process_input
# ---------------------------------------------------------------------------

def process_input(state: AgentState) -> dict:
    plan_log = list(state.get("plan_log") or [])

    if state.get("extracted_content"):
        plan_log.append(f"[{_ts()}] ↩ Reusing extracted content from previous turn.")
        return {"plan_log": plan_log}

    file_path = state.get("file_path") or ""
    user_msg  = state.get("user_message") or ""
    low_fp    = file_path.lower()
    result    = None

    if low_fp.endswith(".pdf"):
        plan_log.append(f"[{_ts()}] 📄 Processing PDF: {os.path.basename(file_path)}")
        result = extract_text_from_pdf(file_path)
    elif low_fp.endswith((".jpg", ".jpeg", ".png")):
        plan_log.append(f"[{_ts()}] 🖼 Processing image: {os.path.basename(file_path)}")
        result = extract_text_from_image(file_path)
    elif low_fp.endswith((".mp3", ".wav", ".m4a")):
        plan_log.append(f"[{_ts()}] 🎵 Processing audio: {os.path.basename(file_path)}")
        result = transcribe_audio(file_path)
    elif "youtube.com" in user_msg or "youtu.be" in user_msg:
        plan_log.append(f"[{_ts()}] ▶ Fetching YouTube transcript")
        result = get_youtube_transcript(user_msg)

    if result is None:
        plan_log.append(f"[{_ts()}] 💬 Text-only input; no extraction needed.")
        return {"plan_log": plan_log, "tool_meta": {}}

    if not result["ok"]:
        err = result.get("error", "Unknown extraction error.")
        plan_log.append(f"[{_ts()}] ✗ Extraction failed: {err}")
        return {
            "extracted_content": f"[Extraction error: {err}]",
            "tool_meta":         result.get("meta", {}),
            "plan_log":          plan_log,
        }

    content = result["content"]
    meta    = result.get("meta", {})

    method     = meta.get("method", "")
    confidence = meta.get("confidence")
    conf_str   = f" | confidence: {confidence:.0%}" if confidence is not None else ""
    plan_log.append(f"[{_ts()}] ✓ Extracted {len(content)} chars via {method}{conf_str}")

    if meta.get("source_type") == "audio":
        dur  = meta.get("duration", "unknown")
        lang = meta.get("language", "auto")
        plan_log.append(f"[{_ts()}] 🎵 Duration: {dur}  |  Language: {lang}")

    if meta.get("truncated"):
        plan_log.append(
            f"[{_ts()}] ⚠ Scanned PDF: OCR'd {meta.get('ocr_pages')} of "
            f"{meta.get('pages')} pages (cap: {os.getenv('MAX_OCR_PAGES', 8)})."
        )

    content, plan_log = _truncate(content, plan_log)

    return {"extracted_content": content, "tool_meta": meta, "plan_log": plan_log}


# ---------------------------------------------------------------------------
# Node: planner
# ---------------------------------------------------------------------------

def planner(state: AgentState) -> dict:
    plan_log = list(state.get("plan_log") or [])
    user_msg = state.get("user_message") or ""
    content  = state.get("extracted_content") or ""
    meta     = state.get("tool_meta") or {}

    source     = meta.get("source_type", "text" if not state.get("file_path") else "file")
    has_content = bool(content.strip())
    looks_code = bool(re.search(r"(def |class |import |#include|function )", user_msg + content[:500]))
    looks_url  = "youtube.com" in user_msg or "youtu.be" in user_msg

    if looks_url:
        tasks = ["fetch_transcript", "summarize_or_chat"]
    elif source == "audio":
        tasks = ["transcription_done", "summarize"]
    elif source in ("image", "pdf"):
        tasks = ["extraction_done", "await_instruction_or_classify"]
    elif looks_code:
        tasks = ["code_explain"]
    else:
        tasks = ["classify_intent", "execute_or_clarify"]

    plan_lines = [
        f"Source: {source}",
        f"Has content: {has_content}",
        f"Likely task(s): {', '.join(tasks)}",
        "Steps: process_input → planner → classify → [clarify | execute] → respond",
    ]
    plan_str = "\n".join(plan_lines)
    plan_log.append(f"[{_ts()}] 📋 Plan:\n{plan_str}")

    return {"current_plan": plan_str, "plan_log": plan_log}


# ---------------------------------------------------------------------------
# Node: classify
# ---------------------------------------------------------------------------

_CLASSIFY_SYS = """
Classify the user's intent into exactly one of:
  summarize      – user wants a summary of content
  sentiment      – user wants sentiment analysis
  code_explain   – user wants code explained / bugs found
  chat           – general question or conversation
  ambiguous      – intent is genuinely unclear

Rules:
- If audio content was provided and the user gave no specific instruction, return summarize.
- If a file was provided but the user gave no instruction, return ambiguous.
- Output ONLY a JSON object with keys "intent" and "missing_info".
  "missing_info" is a short follow-up question when ambiguous, otherwise null.
- No markdown, no prose, only JSON.

Examples:
{"intent": "summarize", "missing_info": null}
{"intent": "ambiguous", "missing_info": "What would you like me to do with this document — summarize it, extract action items, or something else?"}
""".strip()


def classify(state: AgentState) -> dict:
    plan_log = list(state.get("plan_log") or [])
    user_msg = state.get("user_message") or ""
    content  = state.get("extracted_content") or ""
    meta     = state.get("tool_meta") or {}

    content_preview = content[:1000] if content else ""
    source_hint = ""
    if meta.get("source_type") == "audio":
        source_hint = "\nNote: the content is from an audio transcription."

    prompt = f"User: {user_msg}\nExtracted content (preview): {content_preview}{source_hint}"
    try:
        r = invoke_llm(
            [SystemMessage(content=_CLASSIFY_SYS), HumanMessage(content=prompt)],
            plan_log,
        )
        m = re.search(r"\{[\s\S]*?\}", r.content)
        d = json.loads(m.group(0)) if m else {"intent": "chat", "missing_info": None}
    except Exception:
        d = {"intent": "chat", "missing_info": None}

    intent  = d.get("intent", "chat")
    missing = d.get("missing_info")

    # Phase 4.3 — audio always summarizes when classifier falls back to chat
    if meta.get("source_type") == "audio" and intent == "chat" and not user_msg.strip():
        intent = "summarize"
        plan_log.append(f"[{_ts()}] 🔄 Audio with no instruction → overriding intent to 'summarize'")

    plan_log.append(f"[{_ts()}] 🔍 Classified intent: {intent}")
    return {"intent": intent, "missing_info": missing, "plan_log": plan_log}


# ---------------------------------------------------------------------------
# Node: clarify
# ---------------------------------------------------------------------------

def clarify(state: AgentState) -> dict:
    plan_log = list(state.get("plan_log") or [])
    question = state.get("missing_info") or "Could you clarify what you'd like me to do?"
    plan_log.append(f"[{_ts()}] ❓ Asking clarification: {question}")
    return {
        "agent_response": question,
        "action_taken":   "ask_clarification",
        "plan_log":       plan_log,
    }


# ---------------------------------------------------------------------------
# Node: execute
# ---------------------------------------------------------------------------

_TASK_PROMPTS = {
    "summarize": (
        "Summarize the following content. Structure your response as:\n"
        "**One-line summary:** <single sentence>\n\n"
        "**Key points:**\n- bullet 1\n- bullet 2\n- bullet 3\n\n"
        "**Detailed summary:** <exactly 5 sentences>"
    ),
    "sentiment": (
        "Perform sentiment analysis. Structure your response as:\n"
        "**Label:** Positive | Negative | Neutral\n"
        "**Confidence:** <0.0–1.0>\n"
        "**Justification:** <one sentence explaining the sentiment>"
    ),
    "code_explain": (
        "Analyse the following code. Structure your response as:\n"
        "**Language:** <detected programming language>\n"
        "**What it does:** <clear explanation>\n"
        "**Potential bugs:** <list any bugs or 'None found'>\n"
        "**Time complexity:** <Big-O and brief explanation>"
    ),
    "chat": "Provide a helpful, friendly, concise answer to the user's message.",
}


def execute(state: AgentState) -> dict:
    plan_log = list(state.get("plan_log") or [])
    intent   = state.get("intent", "chat")
    user_msg = state.get("user_message") or ""
    content  = state.get("extracted_content") or ""
    meta     = state.get("tool_meta") or {}
    history  = list(state.get("chat_history") or [])

    task_prompt = _TASK_PROMPTS.get(intent, _TASK_PROMPTS["chat"])
    plan_log.append(f"[{_ts()}] ⚙ Executing task: {intent}")

    # Metadata footer (duration, language, OCR confidence)
    meta_lines = []
    if meta.get("duration"):
        meta_lines.append(f"Audio duration: {meta['duration']}")
    if meta.get("language") and meta["language"] not in ("auto", "unknown"):
        meta_lines.append(f"Detected language: {meta['language']}")
    if meta.get("confidence") is not None and meta.get("source_type") in ("image", "pdf"):
        meta_lines.append(f"OCR confidence: {meta['confidence']:.0%}")
    if meta.get("truncated"):
        meta_lines.append(
            f"Note: document was truncated to first {MAX_CONTENT_CHARS} chars."
        )
    meta_footer = ("\n\n---\nMetadata:\n" + "\n".join(meta_lines)) if meta_lines else ""

    full_prompt = (
        f"{task_prompt}\n\n"
        f"User message: {user_msg}\n\n"
        f"Content:\n{content}"
        f"{meta_footer}"
    )

    # Phase 4.4 — pass conversation history for "chat" intent
    if intent == "chat" and history:
        recent = history[-MAX_HISTORY:]
        messages: list = []
        for turn in recent:
            role = turn.get("role", "")
            text = turn.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=text))
            elif role == "assistant":
                messages.append(AIMessage(content=text))
        messages.append(HumanMessage(content=full_prompt))
    else:
        messages = [HumanMessage(content=full_prompt)]

    try:
        r             = invoke_llm(messages, plan_log)
        response_text = r.content
    except Exception as exc:
        response_text = f"I encountered an error generating a response: {exc}"

    # Always surface audio duration in the response text
    if meta.get("source_type") == "audio" and meta.get("duration"):
        if "duration" not in response_text.lower():
            response_text += f"\n\n**Duration:** {meta['duration']}"
        lang = meta.get("language")
        if lang and lang not in ("auto", "unknown") and "language" not in response_text.lower():
            response_text += f"\n**Detected language:** {lang}"

    plan_log.append(f"[{_ts()}] ✓ Response generated ({len(response_text)} chars).")

    # Update conversation history (Phase 4.4)
    updated_history = list(history) + [
        {"role": "user",      "content": user_msg},
        {"role": "assistant", "content": response_text},
    ]
    # Keep only last MAX_HISTORY * 2 entries (pairs)
    updated_history = updated_history[-(MAX_HISTORY * 2):]

    return {
        "agent_response":    response_text,
        "action_taken":      intent,
        "extracted_content": state.get("extracted_content"),
        "chat_history":      updated_history,
        "plan_log":          plan_log,
    }


# ---------------------------------------------------------------------------
# Routing + compile
# ---------------------------------------------------------------------------

def route_after_classify(state: AgentState) -> str:
    return "clarify" if state.get("intent") == "ambiguous" else "execute"


workflow = StateGraph(AgentState)
workflow.add_node("process_input", process_input)
workflow.add_node("planner",       planner)
workflow.add_node("classify",      classify)
workflow.add_node("clarify",       clarify)
workflow.add_node("execute",       execute)

workflow.set_entry_point("process_input")
workflow.add_edge("process_input", "planner")
workflow.add_edge("planner",       "classify")
workflow.add_conditional_edges(
    "classify",
    route_after_classify,
    {"clarify": "clarify", "execute": "execute"},
)
workflow.add_edge("clarify", END)
workflow.add_edge("execute", END)

_checkpointer = MemorySaver()
app = workflow.compile(checkpointer=_checkpointer)
