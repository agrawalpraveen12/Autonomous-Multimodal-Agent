from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
import os, json, re
from .state import AgentState
from tools.ocr import extract_text_from_pdf, extract_text_from_image
from tools.audio import transcribe_audio
from tools.youtube import get_youtube_transcript

llm = ChatGroq(
    model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0
)

input_processor = lambda s: {
    "extracted_content":
        s.get("extracted_content")
        or
        (
            extract_text_from_pdf(s["file_path"])
            if str(s.get("file_path","")).lower().endswith(".pdf")
            else extract_text_from_image(s["file_path"])
            if str(s.get("file_path","")).lower().endswith((".jpg",".jpeg",".png"))
            else transcribe_audio(s["file_path"])
            if str(s.get("file_path","")).lower().endswith((".mp3",".wav",".m4a"))
            else get_youtube_transcript(s["user_message"])
            if ("youtube.com" in str(s.get("user_message","")) or "youtu.be" in str(s.get("user_message","")))
            else ""
        )
}

def intent_classifier(state: AgentState):
    sys = """
    You classify intent: summarize, sentiment, code_explain, chat, ambiguous.
    If unclear → ambiguous. Output JSON only:
    {"intent": "...", "missing_info": "..."}
    """
    prompt = f"User: {state.get('user_message')}\\nContent: {state.get('extracted_content', '')}"
    r = llm.invoke([SystemMessage(content=sys), HumanMessage(content=prompt)])
    m = re.search(r"\{[\s\S]*\}", r.content)
    d = json.loads(m.group(0)) if m else {"intent": "chat", "missing_info": None}
    return {"intent": d.get("intent"), "missing_info": d.get("missing_info")}

clarify_node = lambda s: {
    "agent_response": s.get("missing_info"),
    "action_taken": "ask_clarification"
}

def execution_node(state: AgentState):
    tasks = {
        "summarize": "Summarize in 1 line, 3 bullets, 5 sentences.",
        "sentiment": "Sentiment → label, confidence, justification.",
        "code_explain": "Explain code → what it does, bugs, time complexity.",
        "chat": "Helpful answer."
    }
    inst = tasks.get(state.get("intent"), "Help the user.")
    p = f"Task: {inst}\\nUser: {state.get('user_message')}\\nContent: {state.get('extracted_content', '')}"
    r = llm.invoke([HumanMessage(content=p)])
    return {
        "agent_response": r.content,
        "action_taken": state.get("intent"),
        "extracted_content": state.get("extracted_content")
    }

workflow = StateGraph(AgentState)
workflow.add_node("process_input", input_processor)
workflow.add_node("classify", intent_classifier)
workflow.add_node("clarify", clarify_node)
workflow.add_node("execute", execution_node)
workflow.set_entry_point("process_input")
workflow.add_edge("process_input", "classify")

route = lambda s: (
    "clarify"
    if s.get("intent") == "ambiguous"
    else "execute"
)

workflow.add_conditional_edges(
    "classify",
    route,
    {"clarify": "clarify", "execute": "execute"}
)

workflow.add_edge("clarify", END)
workflow.add_edge("execute", END)

app = workflow.compile()
