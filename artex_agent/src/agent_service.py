# artex_agent/src/agent_service.py
from typing import Dict, Any, Optional, List, Tuple
import uuid
import asyncio # For simulating async work if not calling real Gemini yet

# Import logging_config and setup logging first
# This ensures that if this module is run standalone or imported early, logging is available.
try:
    from .logging_config import get_logger
    log = get_logger(__name__)
except ImportError: # Fallback for simple standalone execution if .logging_config isn't found relative
    import logging
    log = logging.getLogger(__name__)
    if not log.handlers:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        log.info("Fallback basic logging configured for agent_service.py as .logging_config was not found via relative import.")


# In-memory store for conversation histories (SIMPLE MVP - NOT FOR PRODUCTION)
# Production would use Redis, a database, or other persistent store.
_conversation_histories: Dict[str, List[Dict[str, Any]]] = {}


class AgentService:
    def __init__(self, gemini_client_instance: Any, system_prompt_text: str, artex_agent_tools_list: List[Any]):
        # In a real app, these would be proper instances
        self.gemini_client = gemini_client_instance # Initialized GeminiClient
        self.system_prompt = system_prompt_text     # Loaded system prompt
        self.tools = artex_agent_tools_list         # Loaded tools
        log.info("AgentService initialized.", gemini_client_type=type(gemini_client_instance).__name__, system_prompt_length=len(system_prompt_text), tools_count=len(artex_agent_tools_list))

    async def _execute_function_call(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        # Placeholder for actual function call execution logic
        # This would involve calling repository methods as seen in agent.py's CLI loop
        # For now, just simulate based on tool name
        log.info(f"AgentService: Simulating execution of tool.", tool_name=tool_name, tool_args=str(tool_args)) # Log args as str
        if tool_name == "get_contrat_details":
            return {"numero_contrat": tool_args.get("numero_contrat"), "details": "Details du contrat XYZ (simulé par AgentService).", "statut_contrat": "Actif"}
        elif tool_name == "open_claim":
            return {"id_sinistre_artex": f"SIN_ASVC_{uuid.uuid4().hex[:6].upper()}", "message": "Déclaration de sinistre enregistrée (simulé par AgentService)."}
        log.warn("Tool not implemented in AgentService simulation.", tool_name=tool_name)
        return {"error": f"Tool '{tool_name}' not implemented in simulation."}

    async def get_reply(self, session_id: str, user_message: str, conversation_id: Optional[str] = None) -> Tuple[str, str, List[Dict[str,Any]]]:
        # 1. Manage Conversation ID & History
        if not conversation_id or conversation_id not in _conversation_histories:
            new_conv_uuid = uuid.uuid4()
            conversation_id = f"conv_{session_id}_{new_conv_uuid.hex[:8]}"
            _conversation_histories[conversation_id] = []
            log.info("New conversation started.", session_id=session_id, conversation_id=conversation_id)
        else:
            log.info("Continuing existing conversation.", session_id=session_id, conversation_id=conversation_id)

        current_history = _conversation_histories[conversation_id]
        current_history.append({"role": "user", "parts": [{"text": user_message}]})

        # 2. Call Gemini (simplified for this step - real call uses GeminiClient)
        log.debug(f"AgentService: Getting reply for user message.", user_message_snippet=user_message[:50], conversation_id=conversation_id)
        log.debug(f"AgentService: Current history for Gemini (first 2 turns):", history_preview=current_history[:2])

        # --- SIMULATED GEMINI RESPONSE (Phase 1 of API development) ---
        # This section would normally parse a real gemini_response_obj
        # For this subtask, we simulate the response.
        # The full logic from agent.py (multi-turn, function calling, db interaction)
        # will be refactored into this service in subsequent steps.

        simulated_agent_text_response = f"Réponse simulée par AgentService à : '{user_message}'."

        # Basic simulation of function call trigger based on keywords
        if "contrat" in user_message.lower() and ("détails" in user_message.lower() or "detail" in user_message.lower()):
            log.info("AgentService: Simulating Gemini function call trigger for 'get_contrat_details'.")
            # In a real scenario, the first Gemini call would return a function_call part.
            # Then _execute_function_call would run, then another Gemini call with the function_response.
            # Here, we just shortcut to a simulated final response.
            simulated_tool_args = {"numero_contrat": "API_SIM_TEST123"} # Extract from user_message if possible
            tool_result = await self._execute_function_call("get_contrat_details", simulated_tool_args)
            simulated_agent_text_response = f"Voici les détails simulés du contrat {simulated_tool_args['numero_contrat']}: {tool_result.get('details')}, Statut: {tool_result.get('statut_contrat')} (via AgentService)."
        elif "sinistre" in user_message.lower() and ("déclarer" in user_message.lower() or "ouvrir" in user_message.lower()):
            log.info("AgentService: Simulating Gemini function call trigger for 'open_claim'.")
            simulated_tool_args = {"numero_contrat": "API_SIM_TEST123", "type_sinistre": "Dégât des eaux (simulé)", "description_sinistre": user_message}
            tool_result = await self._execute_function_call("open_claim", simulated_tool_args)
            simulated_agent_text_response = f"Résultat de la déclaration: {tool_result.get('message')} ID: {tool_result.get('id_sinistre_artex')} (via AgentService)."
        else:
            # Simulate a generic Gemini text response without function calling
            await asyncio.sleep(0.1) # Simulate async work for Gemini
        # --- END SIMULATED GEMINI RESPONSE ---

        current_history.append({"role": "model", "parts": [{"text": simulated_agent_text_response}]})

        # Trim history (optional for MVP, but good practice)
        MAX_HISTORY_API_TURNS = 10 # Number of user/model turn pairs
        if len(current_history) > MAX_HISTORY_API_TURNS * 2 :
           log.debug(f"Trimming conversation history for {conversation_id}", old_len=len(current_history))
           _conversation_histories[conversation_id] = current_history[-(MAX_HISTORY_API_TURNS*2):]
           log.debug(f"History trimmed to {len(_conversation_histories[conversation_id])} entries.")
        else:
            _conversation_histories[conversation_id] = current_history

        log.info("AgentService returning reply.", conversation_id=conversation_id, response_length=len(simulated_agent_text_response))
        return simulated_agent_text_response, conversation_id, current_history

# Example of how AgentService might be used (for testing this file standalone)
async def main_test_agent_service():
    log.info("--- Testing AgentService Standalone ---")

    # Mock GeminiClient and other dependencies for this standalone test
    class MockGeminiClient:
        async def generate_text_response(self, **kwargs):
            log.info("MockGeminiClient.generate_text_response called with kwargs:", kwargs_keys=list(kwargs.keys()))
            # Simulate a simple text response or a function call response
            # For this test, AgentService's own simulation is primary
            return {"text": "Mocked Gemini direct text response."}

    mock_gemini = MockGeminiClient()
    mock_prompt = "System prompt for testing AgentService."
    mock_tools = [] # Empty list for this phase

    service = AgentService(
        gemini_client_instance=mock_gemini,
        system_prompt_text=mock_prompt,
        artex_agent_tools_list=mock_tools
    )

    session_id_test = "test_session_001"

    log.info("Test 1: First message in a new conversation")
    reply1, conv_id1, history1 = await service.get_reply(session_id_test, "Bonjour, c'est un test.")
    log.info("Test 1 Reply", reply=reply1, conv_id=conv_id1, history_len=len(history1))
    # print(f"Reply 1: {reply1} (Conv ID: {conv_id1})")

    log.info("Test 2: Second message in the same conversation")
    reply2, conv_id2, history2 = await service.get_reply(session_id_test, "Je voudrais les détails de mon contrat.", conversation_id=conv_id1)
    log.info("Test 2 Reply", reply=reply2, conv_id=conv_id2, history_len=len(history2))
    # print(f"Reply 2: {reply2} (Conv ID: {conv_id2})")
    assert conv_id1 == conv_id2

    log.info("Test 3: Message to trigger open_claim simulation")
    reply3, conv_id3, history3 = await service.get_reply(session_id_test, "Je veux déclarer un sinistre.", conversation_id=conv_id2)
    log.info("Test 3 Reply", reply=reply3, conv_id=conv_id3, history_len=len(history3))
    # print(f"Reply 3: {reply3} (Conv ID: {conv_id3})")

    log.info("--- AgentService Standalone Test Finished ---")

if __name__ == "__main__":
    asyncio.run(main_test_agent_service())
