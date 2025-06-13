# artex_agent/src/agent_service.py
import uuid
import datetime
import asyncio
from typing import Dict, Any, Optional, List, Tuple

from google.generativeai.types import Part

try:
    from .logging_config import get_logger
    log = get_logger(__name__)
except ImportError:
    import logging
    log = logging.getLogger(__name__)
    if not log.handlers:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        log.info("Fallback basic logging configured for agent_service.py (ImportError).")

from .database import AsyncSessionFactory
from .database_repositories import ContratRepository, SinistreArtexRepository, AdherentRepository
from .gemini_client import extract_usage_metadata # NEW IMPORT

_conversation_histories: Dict[str, List[Dict[str, Any]]] = {}
MAX_HISTORY_TURNS_API = 10

class AgentService:
    def __init__(self, gemini_client_instance: Any, system_prompt_text: str, artex_agent_tools_list: List[Any]):
        self.gemini_client = gemini_client_instance
        self.system_prompt = system_prompt_text
        self.tools = artex_agent_tools_list
        log.info("AgentService initialized with real Gemini client, system prompt, and tools.")

    async def _execute_function_call(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]: # Removed session from args, using factory inside
        log.info("Executing function call in AgentService", tool_name=tool_name, args_keys=list(tool_args.keys()))
        function_response_content = {"error": f"Tool '{tool_name}' execution failed or not implemented in AgentService."}

        if not AsyncSessionFactory:
            log.error("AsyncSessionFactory not available. Cannot execute function call.", tool_name=tool_name)
            return {"error": "Database session factory not configured."}

        async with AsyncSessionFactory() as session:
            try:
                if tool_name == "get_contrat_details":
                    numero_contrat = tool_args.get("numero_contrat")
                    if numero_contrat:
                        contrat_repo = ContratRepository(session)
                        data = await contrat_repo.get_contrat_details_for_function_call(numero_contrat)
                        function_response_content = data if data else {"error": f"Contrat non trouvé pour le numéro : {numero_contrat}."}
                    else:
                        function_response_content = {"error": "Numéro de contrat manquant pour get_contrat_details."}

                elif tool_name == "open_claim":
                    # ... (implementation as before, ensuring it uses the 'session' from this method)
                    numero_contrat = tool_args.get("numero_contrat")
                    type_sinistre = tool_args.get("type_sinistre")
                    description_sinistre = tool_args.get("description_sinistre")
                    date_survenance_str = tool_args.get("date_survenance")

                    if numero_contrat and type_sinistre and description_sinistre:
                        contrat_repo = ContratRepository(session)
                        contrat = await contrat_repo.get_contrat_by_numero_contrat(numero_contrat, load_full_details=False)
                        if contrat and contrat.id_adherent_principal is not None and contrat.id_contrat is not None:
                            sinistre_repo = SinistreArtexRepository(session)
                            sinistre_data = {
                                "id_contrat": contrat.id_contrat,
                                "id_adherent": contrat.id_adherent_principal,
                                "type_sinistre": type_sinistre,
                                "description_sinistre": description_sinistre,
                                "claim_id_ref": f"CLAIM-{uuid.uuid4().hex[:8].upper()}"
                            }
                            if date_survenance_str:
                                try:
                                    sinistre_data["date_survenance"] = datetime.date.fromisoformat(date_survenance_str)
                                except ValueError:
                                    log.warn("Invalid date_survenance format", date_str=date_survenance_str)
                                    function_response_content = {"error": f"Format de date_survenance invalide : '{date_survenance_str}'. Utilisez YYYY-MM-DD."}

                            if "error" not in function_response_content:
                                new_sinistre = await sinistre_repo.create_sinistre_artex(sinistre_data)
                                await session.commit()
                                function_response_content = {
                                    "id_sinistre_artex": new_sinistre.id_sinistre_artex,
                                    "claim_id_ref": new_sinistre.claim_id_ref,
                                    "message": "Déclaration de sinistre enregistrée avec succès."
                                }
                                log.info("Claim opened successfully via AgentService.", new_sinistre_id=new_sinistre.id_sinistre_artex)
                        else:
                            function_response_content = {"error": f"Contrat non trouvé : {numero_contrat} ou données adhérent/contrat manquantes."}
                    else:
                        function_response_content = {"error": "Infos manquantes pour ouvrir sinistre."}
                # ... (other tool handlers) ...
            except Exception as e_tool:
                await session.rollback()
                log.error(f"Error during tool execution '{tool_name}'", error_str=str(e_tool), exc_info=True) # Use error_str
                function_response_content = {"error": f"Erreur interne lors de l'exécution de l'outil '{tool_name}'."}

        log.info("Function call execution result", tool_name=tool_name, result_summary=str(function_response_content)[:100] + "...")
        return function_response_content

    async def get_reply(
        self,
        session_id: str,
        user_message: str,
        conversation_id: Optional[str] = None,
        request_metadata: Optional[Dict[str, Any]] = None # New metadata param
    ) -> Tuple[str, str, List[Dict[str,Any]], Dict[str, int]]: # Added Dict[str, int] for usage

        log.info("AgentService.get_reply called", session_id=session_id, conversation_id=conversation_id, message_snippet=user_message[:50], metadata_keys=list(request_metadata.keys()) if request_metadata else [])

        accumulated_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        if not self.gemini_client:
            log.error("GeminiClient not initialized in AgentService. Cannot process reply.")
            return "Erreur: Service agent non configuré correctement.", conversation_id or f"error_conv_{uuid.uuid4().hex[:4]}", [], accumulated_usage

        if not conversation_id or conversation_id not in _conversation_histories:
            new_conv_uuid = uuid.uuid4()
            conversation_id = f"api_conv_{session_id}_{new_conv_uuid.hex[:8]}"
            _conversation_histories[conversation_id] = []
            log.info("New conversation started for API", conversation_id=conversation_id)

        current_history = _conversation_histories[conversation_id]
        current_history.append({"role": "user", "parts": [{"text": user_message}]})

        final_agent_text_response = "Je suis désolé, une erreur technique est survenue lors de la génération de ma réponse."

        try:
            log.debug("Calling Gemini (initial or after user message)", conversation_id=conversation_id, history_length=len(current_history))
            gemini_response_obj = await self.gemini_client.generate_text_response(
                prompt_parts=current_history,
                system_instruction=self.system_prompt,
                tools_list=self.tools
            )
            usage_turn1 = extract_usage_metadata(gemini_response_obj)
            for key in accumulated_usage: accumulated_usage[key] += usage_turn1.get(key, 0)
            log.debug("Gemini Turn 1 usage", conversation_id=conversation_id, **usage_turn1)

            candidate = gemini_response_obj.candidates[0] if gemini_response_obj.candidates else None
            function_call_part = None
            if candidate and candidate.content and candidate.content.parts:
                for part_instance in candidate.content.parts: # Renamed 'part' to 'part_instance' to avoid conflict with imported 'Part'
                    if part_instance.function_call:
                        function_call_part = part_instance
                        break

            if function_call_part:
                fc = function_call_part.function_call
                log.info("Gemini requested function call", tool_name=fc.name, args_str=str(dict(fc.args))[:100]+"...", conversation_id=conversation_id)
                current_history.append({"role": "model", "parts": [Part(function_call=fc)]})

                tool_result_dict = await self._execute_function_call(fc.name, dict(fc.args))
                current_history.append({"role": "function", "parts": [Part(function_response={"name": fc.name, "response": tool_result_dict})]})

                log.debug("Calling Gemini again with function response", conversation_id=conversation_id, history_length=len(current_history))
                gemini_response_obj_after_tool = await self.gemini_client.generate_text_response(
                    prompt_parts=current_history,
                    system_instruction=self.system_prompt,
                    tools_list=self.tools
                )
                usage_turn2 = extract_usage_metadata(gemini_response_obj_after_tool)
                for key in accumulated_usage: accumulated_usage[key] += usage_turn2.get(key, 0)
                log.debug("Gemini Turn 2 (after tool) usage", conversation_id=conversation_id, **usage_turn2)

                candidate_after_tool = gemini_response_obj_after_tool.candidates[0] if gemini_response_obj_after_tool.candidates else None
                if candidate_after_tool and candidate_after_tool.content and candidate_after_tool.content.parts:
                    final_agent_text_response = "".join(p.text for p in candidate_after_tool.content.parts if p.text) # Use p here
                    if not final_agent_text_response:
                         fc_after_tool = None
                         for p_instance in candidate_after_tool.content.parts: # Use p_instance here
                             if p_instance.function_call: fc_after_tool = p_instance.function_call; break
                         if fc_after_tool:
                             log.warn("Chained function call detected. Responding with placeholder.", tool_name=fc_after_tool.name, conversation_id=conversation_id)
                             final_agent_text_response = f"[AGENT_ACTION: Outil '{fc_after_tool.name}' suggéré, traitement en attente.]"
                         else:
                             log.warn("No text in Gemini response after function call and no further function call.", conversation_id=conversation_id)
                             final_agent_text_response = "[Réponse de l'agent non disponible après l'outil.]"
                else:
                    log.warn("No valid candidates or parts in Gemini response after function call.", conversation_id=conversation_id)
                    final_agent_text_response = "[Erreur de communication avec l'IA après l'outil.]"
            elif candidate and candidate.content and candidate.content.parts: # Direct text response
                final_agent_text_response = "".join(p.text for p in candidate.content.parts if p.text) # Use p here
                if not final_agent_text_response:
                     log.warn("No text parts in Gemini's direct response.", conversation_id=conversation_id)
                     final_agent_text_response = "[L'agent n'a pas fourni de réponse textuelle.]"
            else:
                log.warn("No valid candidates or parts in initial Gemini response.", conversation_id=conversation_id)
                final_agent_text_response = "[Erreur de communication avec l'IA.]"

            current_history.append({"role": "model", "parts": [{"text": final_agent_text_response}]})

        except Exception as e:
            log.error("Error in AgentService.get_reply", error_str=str(e), exc_info=True, conversation_id=conversation_id) # Use error_str
            if not current_history or current_history[-1]['role'] != 'model':
                 current_history.append({"role": "model", "parts": [{"text": final_agent_text_response}]})

        if len(current_history) > MAX_HISTORY_TURNS_API * 4:
            num_to_trim = len(current_history) - (MAX_HISTORY_TURNS_API * 4)
            _conversation_histories[conversation_id] = current_history[num_to_trim:]
            log.debug(f"Trimmed conversation history for {conversation_id}, removed {num_to_trim} items.")
        else:
            _conversation_histories[conversation_id] = current_history

        log.info("AgentService.get_reply finished", conversation_id=conversation_id, response_snippet=final_agent_text_response[:50]+"...", usage=accumulated_usage)
        return final_agent_text_response, conversation_id, current_history, accumulated_usage

async def main_test_agent_service():
    log.info("--- Testing AgentService Standalone (with Real Logic Simulation & Usage) ---")

    from .gemini_client import GeminiClient
    from .gemini_tools import ARGO_AGENT_TOOLS
    from .agent import load_prompt, DEFAULT_SYSTEM_PROMPT
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

    session_id_test = "test_session_usage_001"
    test_metadata = {"source": "standalone_test"}

    log.info("Test 1: First message (simple)")
    reply1, conv_id1, _, usage1 = await service.get_reply(session_id_test, "Bonjour, comment ça va ?", request_metadata=test_metadata)
    log.info("Test 1 Reply", reply_snippet=reply1[:60]+"...", conv_id=conv_id1, usage=usage1)

    log.info("Test 2: Second message (potential tool use - get_contrat_details)")
    reply2, conv_id2, _, usage2 = await service.get_reply(session_id_test, "Je voudrais les détails de mon contrat NC123.", conversation_id=conv_id1, request_metadata=test_metadata)
    log.info("Test 2 Reply", reply_snippet=reply2[:60]+"...", conv_id=conv_id2, usage=usage2)

    log.info("Test 3: Third message (potential tool use - open_claim)")
    reply3, conv_id3, _, usage3 = await service.get_reply(session_id_test, "Je veux déclarer un sinistre pour NC123, c'est un dégât des eaux.", conversation_id=conv_id2, request_metadata=test_metadata)
    log.info("Test 3 Reply", reply_snippet=reply3[:60]+"...", conv_id=conv_id3, usage=usage3)

    log.info("--- AgentService Standalone Test Finished ---")

if __name__ == "__main__":
    from dotenv import load_dotenv
    import os
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path=dotenv_path)
        log.info(f"Standalone test: Loaded .env from {dotenv_path}")
    else:
        log.warn("Standalone test: .env file not found, relying on environment variables.")

    asyncio.run(main_test_agent_service())
