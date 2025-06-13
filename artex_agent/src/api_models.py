# artex_agent/src/api_models.py
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List # Keep List if used by commented out examples

class ChatMessageRequest(BaseModel):
    session_id: str = Field(
        ...,
        description="A unique identifier for the user's session or device.",
        examples=["user_session_12345"]
    )
    user_message: str = Field( # Renamed from 'message'
        ...,
        description="The text message from the user.",
        examples=["Bonjour, comment allez-vous ?"]
    )
    conversation_id: Optional[str] = Field(
        None,
        description="Optional ID to track an ongoing conversation. If None, a new conversation might be initiated.",
        examples=["conv_abc_789"]
    )
    metadata: Optional[Dict[str, Any]] = Field( # Added metadata field
        None,
        description="Optional metadata about the request (e.g., language, channel hints).",
        examples=[{"language": "fr-FR", "source_channel": "web_chat"}]
    )

class TokenUsage(BaseModel): # New model for usage stats
    prompt_tokens: int = Field(default=0, description="Tokens used in the prompt.")
    completion_tokens: int = Field(default=0, description="Tokens generated in the completion.")
    total_tokens: int = Field(default=0, description="Total tokens used (prompt + completion).")


class ChatMessageResponse(BaseModel):
    assistant_message: str = Field( # Renamed from 'agent_response'
        ...,
        description="The text response from the AI assistant."
    )
    conversation_id: str = Field(
        ...,
        description="Identifier for the current conversation. Can be used in subsequent requests."
    )
    usage: TokenUsage = Field( # Added usage field, using the new TokenUsage model
        default_factory=TokenUsage, # Provides default {prompt:0, completion:0, total:0}
        description="Token usage statistics for the generation of this response."
    )
    debug_info: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional field for debugging or trace information."
    )

# Keep other commented-out examples if they are still relevant for future reference
# class AgentAction(BaseModel):
#     tool_name: str
#     tool_args: Dict[str, Any]

# class RichChatMessageResponse(ChatMessageResponse):
#     suggested_actions: Optional[List[str]] = None
#     requires_action: Optional[AgentAction] = None
