from typing import Optional, List, Dict
from langgraph.graph import MessagesState

class AgentState(MessagesState):
    user_message: Optional[str] = None
    extracted_content: Optional[str] = None
    intent: Optional[str] = None
    missing_info: Optional[str] = None
    action_taken: Optional[str] = None
    agent_response: Optional[str] = None
    file_path: Optional[str] = None
    chat_history: List[Dict] = []
    plan_log: List[str] = []

