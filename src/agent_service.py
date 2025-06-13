# artex_agent/src/agent_service.py
import uuid
import datetime
import asyncio
from typing import Dict, Any, Optional, List, Tuple, AsyncGenerator

try:
    from .logging_config import get_logger
    log = get_logger(__name__)
except ImportError:
    import logging
    log = logging.getLogger(__name__)
    if not log.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        log.info("Fallback basic logging configured for agent_service.py (ImportError).")

from .database import AsyncSessionFactory
from .database_repositories import (
    ContratRepository, SinistreArtexRepository, AdherentRepository
)
from .gemini_client import extract_usage_metadata  # for usage stats

_conversation_histories: Dict[str, List[Dict[str, Any]]] = {}
MAX_HISTORY_TURNS_API = 10

class AgentService:
    def __init__(
        self,
        gemini_client_instance: Any,
        system_prompt_text: str,
        artex_agent_tools_list: List[Any]
    ):
        self.gemini_client = gemini_client_instance
        self.system_prompt = system_prompt_text
        self.tools = artex_agent_tools_list
        log.info(
            "AgentService initialized with Gemini Live client, system prompt, and tools."
        )

    async def _execute_function_call(
        self,
        tool_name: str,
        tool_args: Dict[str, Any]
    ) -> Dict[str, Any]:
        log.info(
            "Executing function call", tool_name=tool_name,
            args_keys=list(tool_args.keys())
        )
        response = {"error": f"Tool '{tool_name}' execution failed."}

        async with AsyncSessionFactory() as session:
            try:
                if tool_name == "get_contrat_details":
                    numero = tool_args.get("numero_contrat")
                    if numero:
                        repo = ContratRepository(session)
                        data = await repo.get_contrat_details_for_function_call(numero)
                        response = data or {"error": f"Contrat {numero} non trouvé."}
                    else:
                        response = {"error": "numero_contrat manquant."}

                elif tool_name == "open_claim":
                    numero = tool_args.get("numero_contrat")
                    type_s = tool_args.get("type_sinistre")
                    desc = tool_args.get("description_sinistre")
                    date_str = tool_args.get("date_survenance")
                    if numero and type_s and desc:
                        c_repo = ContratRepository(session)
                        contrat = await c_repo.get_contrat_by_numero_contrat(
                            numero, load_full_details=False
                        )
                        if contrat and contrat.id_adherent_principal:
                            s_repo = SinistreArtexRepository(session)
                            sinistre = {
                                "id_contrat": contrat.id_contrat,
                                "id_adherent": contrat.id_adherent_principal,
                                "type_sinistre": type_s,
                                "description_sinistre": desc,
                                "claim_id_ref": f"CLAIM-{uuid.uuid4().hex[:8].upper()}"
                            }
                            if date_str:
                                try:
                                    sinistre["date_survenance"] = datetime.date.fromisoformat(date_str)
                                except ValueError:
                                    response = {"error": f"Date invalide: {date_str}. Use YYYY-MM-DD."}
                            if "error" not in response:
                                new_s = await s_repo.create_sinistre_artex(sinistre)
                                await session.commit()
                                response = {
                                    "id_sinistre_artex": new_s.id_sinistre_artex,
                                    "claim_id_ref": new_s.claim_id_ref,
                                    "message": "Sinistre enregistré."
                                }
                        else:
                            response = {"error": f"Contrat {numero} non trouvé."}
                    else:
                        response = {"error": "Paramètres pour sinistre manquants."}

                # add other tools here...
            except Exception as e:
                await session.rollback()
                log.error(
                    "Tool execution error", tool_name=tool_name,
                    error_str=str(e), exc_info=True
                )
                response = {"error": "Erreur interne lors de l'appel d'outil."}

        log.info("Function call result", tool_name=tool_name,
                 result_summary=str(response)[:100])
        return response

    async def get_reply(
        self,
        session_id: str,
        user_message: str,
        conversation_id: Optional[str] = None,
        request_metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, str, List[Dict[str,Any]], Dict[str,int]]:
        log.info(
            "AgentService.get_reply start",
            session_id=session_id,
            conv_id=conversation_id,
            snippet=user_message[:50]
        )
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        # initialize history
        if not conversation_id or conversation_id not in _conversation_histories:
            conversation_id = f"conv_{session_id}_{uuid.uuid4().hex[:8]}"
            _conversation_histories[conversation_id] = []
        history = _conversation_histories[conversation_id]
        history.append({"role": "user", "parts": [{"text": user_message}]})

        # call Gemini Live
        gem_resp = await self.gemini_client.generate_text_response(
            prompt_parts=history,
            system_instruction=self.system_prompt,
            tools_list=self.tools
        )
        # accumulate usage
        meta = extract_usage_metadata(gem_resp)
        for k in usage: usage[k] += meta.get(k, 0)

        # pick first candidate
        candidate = (gem_resp.candidates or [None])[0]
        tool_call = None
        if candidate and candidate.content:
            for chunk in candidate.content.parts:
                if hasattr(chunk, 'function_call') and chunk.function_call:
                    tool_call = chunk.function_call
                    break

        if tool_call:
            history.append({
                "role":"model",
                "parts":[{"function_call": tool_call._asdict()}]
            })
            result = await self._execute_function_call(
                tool_call.name, dict(tool_call.args)
            )
            function_response_part = Part.from_function_response(
                name=tool_call.name,
                response=result
            )
            history.append({
                "role": "function",
                "parts": [function_response_part]
            })
            # second turn
            gem_resp2 = await self.gemini_client.generate_text_response(
                prompt_parts=history,
                system_instruction=self.system_prompt,
                tools_list=self.tools
            )
            meta2 = extract_usage_metadata(gem_resp2)
            for k in usage: usage[k] += meta2.get(k, 0)
            candidate = (gem_resp2.candidates or [None])[0]

        # final text
        text = ""
        if candidate and candidate.content:
            for chunk in candidate.content.parts:
                if hasattr(chunk, 'text') and chunk.text:
                    text += chunk.text
        if not text:
            text = "[Pas de réponse disponible.]"
        history.append({"role":"model","parts":[{"text":text}]})

        # trim history
        if len(history) > MAX_HISTORY_TURNS_API*4:
            _conversation_histories[conversation_id] = history[-MAX_HISTORY_TURNS_API*4:]

        log.info("AgentService.get_reply done", conv_id=conversation_id, response=text[:50])
        return text, conversation_id, history, usage

# standalone test omitted for brevity
