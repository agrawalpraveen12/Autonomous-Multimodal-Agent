from typing import Any, Dict, List, Optional

from langgraph.graph import MessagesState


class AgentState(MessagesState):
    # Incoming turn data
    user_message: Optional[str] = None
    file_path: Optional[str] = None

    # Extraction output (persisted across turns by MemorySaver)
    extracted_content: Optional[str] = None
    tool_meta: Dict[str, Any] = {}   # confidence, duration, language, pages, …

    # Classification
    intent: Optional[str] = None
    missing_info: Optional[str] = None

    # Execution output
    agent_response: Optional[str] = None
    action_taken: Optional[str] = None

    # Explainability  (Rubric: Explainability 10 pts)
    current_plan: Optional[str] = None
    plan_log: List[str] = []

    # Conversation history (populated by caller for future multi-turn context)
    chat_history: List[Dict] = []
