# artex_agent/src/agent_service.py
import uuid
import datetime
import asyncio # Not strictly needed here anymore unless for other async ops
from typing import Dict, Any, Optional, List, Tuple

from google.generativeai.types import Part # For constructing function response parts

try:
    from .logging_config import get_logger
    log = get_logger(__name__)
except ImportError:
    import logging
    log = logging.getLogger(__name__)
    if not log.handlers:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        log.info("Fallback basic logging configured for agent_service.py (ImportError).")

# Database related imports
from .database import AsyncSessionFactory # Assuming this is the factory for creating sessions
from .database_repositories import ContratRepository, SinistreArtexRepository, AdherentRepository # Ensure AdherentRepository is imported if used by tools
# GeminiClient and tools (Tool list) are passed in __init__

# In-memory store for conversation histories (SIMPLE MVP - NOT FOR PRODUCTION)
_conversation_histories: Dict[str, List[Dict[str, Any]]] = {}
MAX_HISTORY_TURNS_API = 10 # Max user/model turn pairs for API history

class AgentService:
    def __init__(self, gemini_client_instance: Any, system_prompt_text: str, artex_agent_tools_list: List[Any]):
        self.gemini_client = gemini_client_instance # Actual GeminiClient instance
        self.system_prompt = system_prompt_text     # System prompt string
        self.tools = artex_agent_tools_list         # List of Tool objects for Gemini
        log.info("AgentService initialized with real Gemini client, system prompt, and tools.")

    async def _execute_function_call(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        log.info("Executing function call in AgentService", tool_name=tool_name, args_keys=list(tool_args.keys()))
        function_response_content = {"error": f"Tool '{tool_name}' execution failed or not implemented in AgentService."}

        if not AsyncSessionFactory:
            log.error("AsyncSessionFactory not available. Cannot execute function call.", tool_name=tool_name)
            return {"error": "Database session factory not configured."}

        async with AsyncSessionFactory() as session: # Create a new session for this function call
            try:
                if tool_name == "get_contrat_details":
                    numero_contrat = tool_args.get("numero_contrat")
                    if numero_contrat:
                        contrat_repo = ContratRepository(session)
                        data = await contrat_repo.get_contrat_details_for_function_call(numero_contrat)
                        if data:
                            function_response_content = data
                        else:
                            function_response_content = {"error": f"Contrat non trouvé pour le numéro : {numero_contrat}."}
                    else:
                        function_response_content = {"error": "Numéro de contrat manquant pour get_contrat_details."}

                elif tool_name == "open_claim":
                    numero_contrat = tool_args.get("numero_contrat")
                    type_sinistre = tool_args.get("type_sinistre")
                    description_sinistre = tool_args.get("description_sinistre")
                    date_survenance_str = tool_args.get("date_survenance")

                    if numero_contrat and type_sinistre and description_sinistre:
                        contrat_repo = ContratRepository(session)
                        contrat = await contrat_repo.get_contrat_by_numero_contrat(numero_contrat, load_full_details=False)
                        if contrat and contrat.id_adherent_principal is not None and contrat.id_contrat is not None:
                            sinistre_repo = SinistreArtexRepository(session) # Using correct name
                            sinistre_data = {
                                "id_contrat": contrat.id_contrat,
                                "id_adherent": contrat.id_adherent_principal,
                                "type_sinistre": type_sinistre,
                                "description_sinistre": description_sinistre,
                                "claim_id_ref": f"CLAIM-{uuid.uuid4().hex[:8].upper()}" # Generate ref here
                            }
                            if date_survenance_str:
                                try:
                                    sinistre_data["date_survenance"] = datetime.date.fromisoformat(date_survenance_str)
                                except ValueError:
                                    log.warn("Invalid date_survenance format", date_str=date_survenance_str)
                                    function_response_content = {"error": f"Format de date_survenance invalide : '{date_survenance_str}'. Utilisez YYYY-MM-DD."}

                            if "error" not in function_response_content: # Proceed if date was okay or not provided
                                new_sinistre = await sinistre_repo.create_sinistre_artex(sinistre_data) # Corrected name
                                await session.commit() # Commit the session after successful creation
                                function_response_content = {
                                    "id_sinistre_artex": new_sinistre.id_sinistre_artex, # Corrected PK name
                                    "claim_id_ref": new_sinistre.claim_id_ref,
                                    "message": "Déclaration de sinistre enregistrée avec succès."
                                }
                                log.info("Claim opened successfully via AgentService.", new_sinistre_id=new_sinistre.id_sinistre_artex)
                        else:
                            function_response_content = {"error": f"Contrat non trouvé pour le numéro : {numero_contrat} ou informations d'adhérent/contrat manquantes."}
                    else:
                        function_response_content = {"error": "Informations manquantes (numéro de contrat, type, description) pour ouvrir le sinistre."}

                # Add other tool handlers here if needed

            except Exception as e_tool:
                await session.rollback() # Rollback on any error during tool execution
                log.error(f"Error during tool execution '{tool_name}'", error=str(e_tool), exc_info=True)
                function_response_content = {"error": f"Erreur interne lors de l'exécution de l'outil '{tool_name}'."}

        log.info("Function call execution result", tool_name=tool_name, result_summary=str(function_response_content)[:100] + "...")
        return function_response_content

    async def get_reply(self, session_id: str, user_message: str, conversation_id: Optional[str] = None) -> Tuple[str, str, List[Dict[str,Any]]]:
        log.info("AgentService.get_reply called", session_id=session_id, conversation_id=conversation_id, message_snippet=user_message[:50])

        if not self.gemini_client:
            log.error("GeminiClient not initialized in AgentService. Cannot process reply.")
            return "Erreur: Service agent non configuré correctement.", conversation_id or "new_conv_error", []

        if not conversation_id or conversation_id not in _conversation_histories:
            new_conv_uuid = uuid.uuid4()
            conversation_id = f"api_conv_{session_id}_{new_conv_uuid.hex[:8]}"
            _conversation_histories[conversation_id] = []
            log.info("New conversation started for API", conversation_id=conversation_id)

        current_history = _conversation_histories[conversation_id]
        current_history.append({"role": "user", "parts": [{"text": user_message}]})

        final_agent_text_response = "Je suis désolé, une erreur technique est survenue lors de la génération de ma réponse." # Default error

        try:
            # First call to Gemini
            log.debug("Calling Gemini (initial or after user message)", conversation_id=conversation_id, history_length=len(current_history))
            gemini_response = await self.gemini_client.generate_text_response(
                prompt_parts=current_history,
                system_instruction=self.system_prompt,
                tools_list=self.tools
            )

            # Check for function call
            # The actual response object structure from gemini_client.generate_text_response needs to be handled here.
            # Assuming it returns an object that has a similar structure to the direct SDK `GenerateContentResponse`
            # where parts might contain a function_call.

            # The GeminiClient returns the raw GenerateContentResponse object from the SDK
            candidate = gemini_response.candidates[0] if gemini_response.candidates else None
            if candidate and candidate.content and candidate.content.parts:
                function_call_part = None
                for part in candidate.content.parts:
                    if part.function_call:
                        function_call_part = part
                        break

                if function_call_part:
                    fc = function_call_part.function_call
                    log.info("Gemini requested function call", tool_name=fc.name, args_str=str(dict(fc.args))[:100]+"...") # Log args snippet

                    current_history.append({"role": "model", "parts": [Part(function_call=fc)]})

                    tool_result = await self._execute_function_call(fc.name, dict(fc.args))

                    current_history.append({"role": "function", "parts": [Part(function_response={"name": fc.name, "response": tool_result})]})

                    log.debug("Calling Gemini again with function response", conversation_id=conversation_id, history_length=len(current_history))
                    gemini_response_after_tool = await self.gemini_client.generate_text_response(
                        prompt_parts=current_history,
                        system_instruction=self.system_prompt,
                        tools_list=self.tools
                    )
                    # Check again for chained calls or errors
                    candidate_after_tool = gemini_response_after_tool.candidates[0] if gemini_response_after_tool.candidates else None
                    if candidate_after_tool and candidate_after_tool.content and candidate_after_tool.content.parts:
                        final_agent_text_response = "".join(part.text for part in candidate_after_tool.content.parts if part.text)
                        if not final_agent_text_response: # If parts exist but no text
                             fc_after_tool = None
                             for part in candidate_after_tool.content.parts:
                                 if part.function_call: fc_after_tool = part.function_call; break
                             if fc_after_tool:
                                 log.warn("Chained function call detected after tool response. Responding with placeholder.", tool_name=fc_after_tool.name)
                                 final_agent_text_response = f"[AGENT_ACTION: Outil '{fc_after_tool.name}' suggéré, traitement en attente.]"
                             else:
                                 log.warn("No text in Gemini response after function call and no further function call.")
                                 final_agent_text_response = "[Réponse de l'agent non disponible après l'outil.]"
                    else: # No candidates or parts after tool call
                        log.warn("No valid candidates or parts in Gemini response after function call.")
                        final_agent_text_response = "[Erreur de communication avec l'IA après l'outil.]"

                else: # No function call in the first response, direct text
                    final_agent_text_response = "".join(part.text for part in candidate.content.parts if part.text)
                    if not final_agent_text_response:
                         log.warn("No text parts in Gemini's direct response.")
                         final_agent_text_response = "[L'agent n'a pas fourni de réponse textuelle.]"
            else: # No candidates or parts in initial response
                log.warn("No valid candidates or parts in initial Gemini response.")
                final_agent_text_response = "[Erreur de communication avec l'IA.]"

            current_history.append({"role": "model", "parts": [{"text": final_agent_text_response}]})

        except Exception as e:
            log.error("Error in AgentService.get_reply during Gemini interaction or tool execution.", error=str(e), exc_info=True)
            # Ensure history still gets the user message and a model error response
            if not current_history or current_history[-1]['role'] != 'model':
                 current_history.append({"role": "model", "parts": [{"text": final_agent_text_response}]})


        # Trim history
        if len(current_history) > MAX_HISTORY_TURNS_API * 2:
            num_to_trim = len(current_history) - (MAX_HISTORY_TURNS_API * 2)
            _conversation_histories[conversation_id] = current_history[num_to_trim:]
            log.debug(f"Trimmed conversation history for {conversation_id}, removed {num_to_trim} items.")
        else:
            _conversation_histories[conversation_id] = current_history

        log.info("AgentService.get_reply finished", conversation_id=conversation_id, response_snippet=final_agent_text_response[:50]+"...")
        return final_agent_text_response, conversation_id, current_history


# Standalone test (similar to before but points to the real implementation)
async def main_test_agent_service():
    log.info("--- Testing AgentService Standalone (with Real Logic Simulation) ---")

    # This test now requires GEMINI_API_KEY and potentially a DB if tools are hit.
    # For a unit-like test, GeminiClient and DB interactions would be mocked.
    # Here, we rely on the actual client, but the DB calls in _execute_function_call
    # are self-contained with AsyncSessionFactory.

    from .gemini_client import GeminiClient # For actual client
    from .gemini_tools import ARGO_AGENT_TOOLS # For actual tools
    from .agent import load_prompt, DEFAULT_SYSTEM_PROMPT # For actual prompt
    from dotenv import load_dotenv
    import os

    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    load_dotenv(dotenv_path=dotenv_path)

    if not os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY") == "YOUR_GEMINI_API_KEY_HERE":
        log.critical("GEMINI_API_KEY not found or is placeholder. Cannot run full AgentService test.")
        return

    gemini_client_instance = GeminiClient()
    system_prompt = load_prompt("system_context.txt", DEFAULT_SYSTEM_PROMPT)

    service = AgentService(
        gemini_client_instance=gemini_client_instance,
        system_prompt_text=system_prompt,
        artex_agent_tools_list=ARGO_AGENT_TOOLS
    )

    session_id_test = "test_session_real_001"

    log.info("Test 1: First message (simple)")
    reply1, conv_id1, history1 = await service.get_reply(session_id_test, "Bonjour, comment ça va ?")
    log.info("Test 1 Reply", reply_snippet=reply1[:60]+"...", conv_id=conv_id1, history_len=len(history1))

    log.info("Test 2: Second message (potential tool use - get_contrat_details)")
    # This requires 'get_contrat_details' tool to be defined in ARGO_AGENT_TOOLS
    # and the DB to be up if Gemini actually tries to call it.
    # For this test, if DB isn't up, the tool call will likely return an error, which Gemini should then summarize.
    reply2, conv_id2, history2 = await service.get_reply(session_id_test, "Je voudrais les détails de mon contrat NC123.", conversation_id=conv_id1)
    log.info("Test 2 Reply", reply_snippet=reply2[:60]+"...", conv_id=conv_id2, history_len=len(history2))

    log.info("Test 3: Third message (potential tool use - open_claim)")
    # This requires 'open_claim' tool
    reply3, conv_id3, history3 = await service.get_reply(session_id_test, "Je veux déclarer un sinistre pour NC123, c'est un dégât des eaux.", conversation_id=conv_id2)
    log.info("Test 3 Reply", reply_snippet=reply3[:60]+"...", conv_id=conv_id3, history_len=len(history3))

    log.info("--- AgentService Standalone Test Finished ---")

if __name__ == "__main__":
    # This ensures .env from project root is loaded if running this file directly from src/
    from dotenv import load_dotenv
    import os
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path=dotenv_path)
        log.info(f"Standalone test: Loaded .env from {dotenv_path}")
    else:
        log.warn("Standalone test: .env file not found, relying on environment variables.")

    asyncio.run(main_test_agent_service())
