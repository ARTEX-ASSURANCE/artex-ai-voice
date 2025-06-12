# artex_agent/src/api_models.py
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

class ChatMessageRequest(BaseModel):
    session_id: str = Field(
        ...,
        description="A unique identifier for the user's session or device.",
        examples=["user_session_12345"]
    )
    message: str = Field(
        ...,
        description="The text message from the user.",
        examples=["Bonjour, comment allez-vous ?"]
    )
    conversation_id: Optional[str] = Field(
        None,
        description="Optional ID to track an ongoing conversation. If None, a new conversation might be initiated.",
        examples=["conv_abc_789"]
    )
    # language: Optional[str] = Field("fr-FR", description="Language code for the request, defaults to French.") # Future use

class ChatMessageResponse(BaseModel):
    agent_response: str = Field(
        ...,
        description="The text response from the AI agent."
    )
    conversation_id: str = Field(
        ...,
        description="Identifier for the current conversation. Can be used in subsequent requests."
    )
    # Placeholder for structured content or rich responses later
    # structured_content: Optional[List[Dict[str, Any]]] = None

    # Placeholder for debug/trace information, not for display to typical users
    # This will be populated by the backend if/when the event emission system is built
    # For MVP, it can be omitted or always None.
    debug_info: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional field for debugging or trace information."
    )

# Example of a more complex response if needed later for function call results etc.
# class AgentAction(BaseModel):
#     tool_name: str
#     tool_args: Dict[str, Any]

# class RichChatMessageResponse(ChatMessageResponse):
#     suggested_actions: Optional[List[str]] = None
#     requires_action: Optional[AgentAction] = None # If backend needs frontend to do something
