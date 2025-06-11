# Standard library imports
import os
import sys # Added import
import asyncio
import tempfile
import time
import json
import argparse
import uuid # Added for generating claim IDs
import datetime # Added for date_survenance in open_claim

# Third-party imports
from dotenv import load_dotenv
import speech_recognition as sr
# from gtts import gTTS # gTTS is now used within TTSService
import pygame
from google.generativeai.types import Part # Added for constructing tool response parts
from pathlib import Path # For TTSService path operations

# Local application imports
import src.database as database
from src.database_repositories import ContratRepository, SinistreArthexRepository
import src.livekit_integration as livekit_integration
from src.gemini_client import GeminiClient
from src.gemini_tools import ARGO_AGENT_TOOLS
from src.asr import ASRService
from src.tts import TTSService # Import the new TTSService
from typing import Optional, List, Dict, Any

# Load environment variables from .env file at the very beginning
load_dotenv()

# Import logging_config and setup logging first
from src.logging_config import setup_logging, get_logger
setup_logging() # Call before any other module that might log
log = get_logger(__name__) # Logger for this module (agent.py)


# --- Prompt Loading ---
DEFAULT_SYSTEM_PROMPT = (
    "Tu es un assistant virtuel pour ARTEX ASSURANCES, nommé Jules.\n"
    "Réponds en français. Sois professionnel et amical.\n"
    "Si une question est ambiguë, demande des précisions en commençant ta réponse par '[CLARIFY]'.\n"
    "Si tu ne peux pas répondre ou si l'utilisateur veut parler à un humain, commence ta réponse par '[HANDOFF]'."
)

def load_prompt(file_name: str, default_prompt: str = DEFAULT_SYSTEM_PROMPT) -> str:
    # Assuming agent.py is in artex_agent/src/
    # So, __file__ is .../artex_agent/src/agent.py
    # os.path.dirname(__file__) is .../artex_agent/src/
    # os.path.join(os.path.dirname(__file__), '..', 'prompts') is .../artex_agent/prompts/
    prompt_dir = os.path.join(os.path.dirname(__file__), '..', 'prompts')
    file_path = os.path.join(prompt_dir, file_name)

    # Ensure this print goes to stderr if it's for debugging the loading process itself
    # print(f"DEBUG: Attempting to load prompt from: {file_path}", file=sys.stderr)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        if not content:
            print(f"CRITICAL WARNING: Prompt file {file_path} is empty. Using default system prompt.", file=sys.stderr)
            # In future, use structlog: log.warning("Prompt file empty...", path=file_path)
            return default_prompt
        return content
    except FileNotFoundError:
        print(f"CRITICAL WARNING: Prompt file {file_path} not found! Using default system prompt. THIS IS A CONFIGURATION ISSUE.", file=sys.stderr)
        # In future, use structlog: log.critical("Prompt file not found...", path=file_path)
        return default_prompt
    except Exception as e:
        print(f"ERROR: Error loading prompt file {file_path}: {e}. Using default system prompt.", file=sys.stderr)
        # In future, use structlog: log.error("Error loading prompt file", path=file_path, error=str(e), exc_info=True)
        return default_prompt

# Existing global ARTEX_SYSTEM_PROMPT initialization should be updated to use this:
ARTEX_SYSTEM_PROMPT = load_prompt("system_context.txt") # Implicitly uses new DEFAULT_SYSTEM_PROMPT
# The if not ARTEX_SYSTEM_PROMPT check is removed as load_prompt now always returns a string.

# --- Global Instances ---
db_engine = None
livekit_room_service_client = None
livekit_room_instance = None
livekit_event_handler_task = None
gemini_chat_client: Optional[GeminiClient] = None
asr_service_global: Optional[ASRService] = None
tts_service_global: Optional[TTSService] = None
_pygame_mixer_initialized = False
args = None
input_mode = "voice"

def configure_services():
    global db_engine, livekit_room_service_client, gemini_chat_client, asr_service_global, tts_service_global
    log.info("Configuring services...")

    if gemini_chat_client is None:
        try:
            gemini_chat_client = GeminiClient()
            log.info("GeminiClient initialized successfully.")
        except Exception as e:
            log.critical("Failed to initialize GeminiClient.", error=str(e), exc_info=True)
            raise

    if db_engine is None:
        if database.db_engine_instance:
            db_engine = database.db_engine_instance
            log.info("Database engine (from database.py) configured successfully.")
        else:
            log.warn("Database engine not available from database.py. DB operations will fail if attempted.")

    if livekit_room_service_client is None:
        try:
            livekit_room_service_client = livekit_integration.get_livekit_room_service()
            log.info("LiveKit RoomServiceClient initialized successfully.")
        except Exception as e:
            log.warn("Failed to initialize LiveKit RoomServiceClient.", error=str(e), exc_info=True)

    if asr_service_global is None:
        try:
            mic_idx = args.mic_index if args and hasattr(args, 'mic_index') else None
            asr_service_global = ASRService(device_index=mic_idx)
            log.info(f"ASRService initialized successfully.", mic_index=(mic_idx if mic_idx is not None else 'Default'))
        except Exception as e:
            log.warn("Failed to initialize ASRService.", error=str(e), exc_info=True)
            asr_service_global = None

    if tts_service_global is None:
        try:
            tts_service_global = TTSService()
            log.info("TTSService initialized successfully.")
        except Exception as e:
            log.warn("Failed to initialize TTSService.", error=str(e), exc_info=True)
            tts_service_global = None
    log.info("Service configuration finished.")


async def generate_agent_response(
    conversation_history: List[Dict[str, Any]],
    tools_list: Optional[List[Tool]] = None
    ) -> Any:
    global gemini_chat_client
    if not gemini_chat_client:
        log.error("Gemini client not initialized before call to generate_agent_response.")
        return "Erreur: Le client Gemini n'est pas initialisé. Veuillez redémarrer l'agent."

    final_tools = tools_list if tools_list is not None else ARGO_AGENT_TOOLS

    try:
        gemini_response_obj = await gemini_chat_client.generate_text_response(
            prompt_parts=conversation_history,
            system_instruction=ARTEX_SYSTEM_PROMPT,
            tools_list=final_tools_list
        )
        return gemini_response_obj
    except Exception as e:
        log.error("Error in generate_agent_response", error=str(e), exc_info=True)
        return "Erreur: Impossible d'obtenir une réponse du modèle IA."

def play_audio_pygame(filepath: str):
    global _pygame_mixer_initialized
    if not _pygame_mixer_initialized:
        try:
            pygame.mixer.init()
            _pygame_mixer_initialized = True
            # log.debug("Pygame mixer initialized for audio playback.")
        except pygame.error as e:
            log.error("Pygame mixer init error. Cannot play audio.", error=str(e))
            return

    if not Path(filepath).exists():
        log.error("Audio file not found for playback.", path=filepath)
        return

    try:
        pygame.mixer.music.load(filepath)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
    except pygame.error as e:
        log.error("Pygame error playing audio.", path=filepath, error=str(e))
    except Exception as e:
        log.error("Unexpected error playing audio.", path=filepath, error=str(e), exc_info=True)

def speak_text_output(text_to_speak: str):
    global livekit_room_instance, tts_service_global

    if not text_to_speak:
        log.warn("No text provided to speak_text_output.")
        return

    if not tts_service_global:
        log.error("TTS Service not available. Cannot speak.")
        # User-facing print remains if TTS is utterly broken, but primary output is via log.
        print(f"Agent (ARTEX) (fallback print): {text_to_speak}")
        return

    mp3_filepath = None
    try:
        mp3_filepath = asyncio.run(tts_service_global.get_speech_audio_filepath(text_to_speak))
    except Exception as e:
        log.error("Error getting speech audio filepath from TTSService.", error_str=str(e), exc_info=True) # Use error_str for consistency
        # User-facing print remains if TTS is utterly broken
        print(f"Agent (ARTEX) (fallback print after TTS error): {text_to_speak}")
        return

    if mp3_filepath:
        if livekit_room_instance:
            log.info(f"Simulating LiveKit TTS publish for text: '{text_to_speak}'", audio_file=mp3_filepath)
            try:
                asyncio.run(livekit_integration.publish_tts_audio_to_room(livekit_room_instance, text_to_speak))
            except Exception as e:
                log.error("Error during (simulated) LiveKit TTS publish.", error=str(e), exc_info=True)
        else:
            play_audio_pygame(mp3_filepath)
    else:
        log.error("TTS failed to generate audio file.", text=text_to_speak)
        print(f"Agent (ARTEX) (fallback print after TTS failure): {text_to_speak}")

async def main_async_logic():
    global livekit_room_instance, livekit_event_handler_task, input_mode, args
    if args and args.livekit_room:
        if not livekit_room_service_client:
            log.error("LiveKit RoomServiceClient not initialized. Cannot join room.")
            return

        log.info(f"Attempting to join LiveKit room: {args.livekit_room} as {args.livekit_identity}")
        livekit_room_instance = await livekit_integration.join_room_and_publish_audio(
            livekit_room_service_client, args.livekit_room, args.livekit_identity)

        if livekit_room_instance:
            log.info(f"Successfully joined LiveKit room.", room_name=args.livekit_room, participant_identity=args.livekit_identity)
            livekit_event_handler_task = asyncio.create_task(livekit_integration.handle_room_events(livekit_room_instance))
            input_mode = "text"
            # User-facing print:
            print("Agent en mode LiveKit. Saisie vocale simulée par entrée texte.") # User-facing, keep
        else:
            log.error("Could not join LiveKit room.", room_name=args.livekit_room)
            # User-facing print:
            print(f"Impossible de rejoindre la room LiveKit: {args.livekit_room}. Retour au mode CLI.") # User-facing, keep
    run_cli_conversation_loop()

def run_cli_conversation_loop():
    global input_mode, args, current_conversation_history
    log.info("Starting CLI conversation loop.", livekit_mode=(livekit_room_instance is not None))

    if not livekit_room_instance:
        # User-facing prints
        print("Dites quelque chose (ou tapez 'texte', 'exit'/'quit').")
        if input_mode == "voice": print("Vous pouvez aussi taper 'texte' pour passer en mode saisie manuelle.")
    else:
        # User-facing print
        print(f"Mode LiveKit actif. Tapez messages pour '{args.livekit_identity_cli_prompt}'. Tapez 'exit' ou 'quit' pour terminer.")

    current_conversation_history = []

    while True:
        user_input = None
        if livekit_room_instance:
            user_input = input(f"Vous ({args.livekit_identity_cli_prompt if args and args.livekit_room else 'texte'}): ") # User-facing
        elif input_mode == "voice":
            if not asr_service_global:
                log.warn("ASR service not available. Switching to text mode.")
                # User-facing print:
                print("Agent (ARTEX): Service ASR non disponible. Passage en mode texte.")
                input_mode = "text"; continue

            # User-facing print:
            print("Agent (ARTEX): Parlez maintenant...")
            user_input_text_chunk = None
            async def get_asr_input(): # Helper to run async gen in sync loop
                async for text_result in asr_service_global.listen_for_speech(): return text_result
                return None
            user_input_text_chunk = asyncio.run(get_asr_input())

            if user_input_text_chunk and not user_input_text_chunk.startswith("[ASR_"):
                log.info("ASR successful.", transcribed_text=user_input_text_chunk)
                # User-facing print:
                print(f"Vous (voix): {user_input_text_chunk}"); user_input = user_input_text_chunk
            else:
                log.warn("ASR failed or returned signal.", asr_signal=user_input_text_chunk)
                # User-facing prints for various ASR issues:
                if user_input_text_chunk == "[ASR_SILENCE_TIMEOUT]": print("Agent (ARTEX): Aucun son détecté.")
                elif user_input_text_chunk == "[ASR_UNKNOWN_VALUE]": print("Agent (ARTEX): Je n'ai pas compris.")
                elif user_input_text_chunk and user_input_text_chunk.startswith("[ASR_REQUEST_ERROR"):
                    print(f"Agent (ARTEX): Erreur ASR: {user_input_text_chunk}")
                elif user_input_text_chunk: print(f"Agent (ARTEX): Signal ASR: {user_input_text_chunk}")
                else: print("Agent (ARTEX): Problème reconnaissance vocale.")

                # User-facing print for retry/switch:
                choice = input("Agent (ARTEX): Réessayer (Entrée) ou 'texte'? ").lower()
                if choice == 'texte':
                    input_mode = "text"; log.info("Switched to text input mode by user choice.")
                    print("Agent (ARTEX): Mode texte.") # User-facing
                continue
        elif input_mode == "text": # Standard text input
            user_input = input("Vous (texte): ") # User-facing
            if user_input.lower() == 'voix':
                input_mode = "voice"; log.info("Switched to voice input mode.")
                print("Agent (ARTEX): Mode vocal.") # User-facing
                continue

        if not user_input: continue # Loop if no input was actually captured
        log.info("User input received.", input_text=user_input, mode=input_mode)

        if user_input.lower() in ['exit', 'quit']:
            log.info("User requested exit."); print("Au revoir!"); break # User-facing
        if not user_input.strip() and not livekit_room_instance:
            log.warn("Empty input received in CLI mode.")
            print("Agent (ARTEX): Demande vide."); continue # User-facing

        log.info("Agent thinking...") # Internal log
        # User-facing print:
        print("Agent (ARTEX): ...pense...")

        if not current_conversation_history or \
           (current_conversation_history and current_conversation_history[-1]['role'] == 'function'):
            current_conversation_history.append({'role': 'user', 'parts': [{'text': user_input}]})
        else: # Overwrite last user message if it wasn't a function sequence (e.g. direct clarification)
             current_conversation_history = [{'role': 'user', 'parts': [{'text': user_input}]}]


        gemini_response_object = asyncio.run(generate_agent_response(current_conversation_history))
        agent_response_text = ""; function_call_to_process = None

        if isinstance(gemini_response_object, str): # Error string from generate_agent_response
            agent_response_text = gemini_response_object
            log.error("Gemini response was an error string.", error_message=agent_response_text)
        elif gemini_response_object.candidates and \
             gemini_response_object.candidates[0].content and \
             gemini_response_object.candidates[0].content.parts:
            for part in gemini_response_object.candidates[0].content.parts:
                if part.function_call:
                    function_call_to_process = part.function_call
                    break
            if not function_call_to_process:
                agent_response_text = gemini_response_object.text if gemini_response_object.text else "[GEMINI_NO_TEXT]"
        else:
            agent_response_text = gemini_response_object.text if hasattr(gemini_response_object, 'text') and gemini_response_object.text else "[GEMINI_EMPTY_CANDIDATE]"
            log.warn("Received unusual Gemini response object structure.", response_obj_type=type(gemini_response_object).__name__, has_text=hasattr(gemini_response_object, 'text'))


        if function_call_to_process:
            tool_name = function_call_to_process.name
            tool_args = dict(function_call_to_process.args)
            log.info("Gemini Function Call triggered.", tool_name=tool_name, tool_args=tool_args)
            # User-facing DEBUG print, changed to log.debug for internal visibility.
            # If truly for user, it would be a different format or a specific user debug mode.
            log.debug("Gemini Function Call details for agent operator.", tool_name=tool_name, tool_args=str(tool_args)) # Convert tool_args to str if it can be complex

            current_conversation_history.append({'role': 'model', 'parts': [Part(function_call=function_call_to_process)]})
            function_response_content = {"error": f"Outil {tool_name} inconnu ou non implémenté."}

            if not db_engine or not database.AsyncSessionFactory:
                log.error("Database not configured, cannot execute function call.", tool_name=tool_name)
                function_response_content = {"error": "DB non configurée."}
            elif tool_name == "get_contrat_details":
                numero_contrat = tool_args.get("numero_contrat")
                if numero_contrat:
                    log.info("Executing tool: get_contrat_details", numero_contrat=numero_contrat)
                    async def _get_details():
                        async with database.AsyncSessionFactory() as session:
                            repo = ContratRepository(session)
                            data = await repo.get_contrat_details_for_function_call(numero_contrat)
                            return data if data else {"error": f"Contrat non trouvé: {numero_contrat}."}
                    try:
                        function_response_content = asyncio.run(_get_details())
                    except Exception as e:
                        log.error("Error executing get_contrat_details", error=str(e), exc_info=True)
                        function_response_content = {"error": f"Erreur interne lors de la recherche du contrat {numero_contrat}."}
                else:
                    log.warn("Missing 'numero_contrat' for get_contrat_details tool.")
                    function_response_content = {"error": "Numéro de contrat manquant."}
            elif tool_name == "open_claim":
                numero_contrat = tool_args.get("numero_contrat")
                type_sinistre = tool_args.get("type_sinistre")
                description_sinistre = tool_args.get("description_sinistre")
                date_survenance_str = tool_args.get("date_survenance")
                if numero_contrat and type_sinistre and description_sinistre:
                    async def _open_claim_op():
                        async with database.AsyncSessionFactory() as session:
                            contrat_repo = ContratRepository(session)
                            contrat = await contrat_repo.get_contrat_by_numero_contrat(numero_contrat)
                            if contrat and contrat.id_adherent_principal is not None and contrat.id_contrat is not None:
                                sinistre_repo = SinistreArthexRepository(session)
                                claim_id_ref_str = f"CLAIM-{uuid.uuid4().hex[:8].upper()}"
                                sinistre_data = {
                                    "claim_id_ref": claim_id_ref_str, "id_contrat": contrat.id_contrat,
                                    "id_adherent": contrat.id_adherent_principal, "type_sinistre": type_sinistre,
                                    "description_sinistre": description_sinistre,
                                }
                                if date_survenance_str:
                                    try: sinistre_data["date_survenance"] = datetime.date.fromisoformat(date_survenance_str)
                                    except ValueError: return {"error": f"Format date invalide: '{date_survenance_str}'."}
                                new_sinistre = await sinistre_repo.create_sinistre_arthex(sinistre_data)
                                await session.commit()
                                return {"id_sinistre_arthex": new_sinistre.id_sinistre_arthex, "claim_id_ref": new_sinistre.claim_id_ref, "message": "Déclaration enregistrée."}
                            return {"error": f"Contrat {numero_contrat} non trouvé."}
                    try: function_response_content = asyncio.run(_open_claim_op())
                    except Exception as e:
                        log.error("Error executing open_claim tool", error_str=str(e), exc_info=True)
                        function_response_content = {"error": f"Erreur interne ouverture sinistre: {e}"}
                else:
                    log.warn("Missing required arguments for open_claim tool.", provided_args=str(tool_args))
                    function_response_content = {"error": "Infos manquantes pour ouvrir sinistre."}

            current_conversation_history.append({'role': 'function', 'parts': [Part(function_response={"name": tool_name, "response": function_response_content})]})
            log.info("Agent thinking (after tool execution)...", tool_name=tool_name) # Replaces user-facing print
            # User-facing print: print(f"Agent (ARTEX): ...pense (après outil {tool_name})...") # Kept for user feedback
            final_gemini_response_obj = asyncio.run(generate_agent_response(current_conversation_history))
            if isinstance(final_gemini_response_obj, str): agent_response_text = final_gemini_response_obj
            elif final_gemini_response_obj.text: agent_response_text = final_gemini_response_obj.text
            else: agent_response_text = "[GEMINI_NO_TEXT_POST_FUNC]"
            current_conversation_history = []

        agent_response = agent_response_text
        if agent_response.startswith("[HANDOFF]"):
            handoff_msg = agent_response.replace("[HANDOFF]", "").strip() or "Je vous mets en relation avec un conseiller."
            # User-facing prints, keep:
            print(f"Agent (ARTEX): {handoff_msg}"); speak_text_output(handoff_msg)
            log.info("Conversation ended due to HANDOFF signal.", handoff_message=handoff_msg)
            print("Conversation terminée (handoff)."); break
        elif agent_response.startswith("[CLARIFY]"):
            clarify_q = agent_response.replace("[CLARIFY]", "").strip()
            # User-facing prints, keep:
            print(f"Agent (ARTEX) précisions: {clarify_q}"); speak_text_output(clarify_q)
            log.info("Clarification requested by agent.", question=clarify_q)
            current_conversation_history.append({'role': 'model', 'parts': [{'text': agent_response}]})
            user_clarification = None; current_clar_mode = input_mode # These are user-facing prompts/interactions
            if livekit_room_instance:
                 print("Clarification (LiveKit - Sim):"); user_clarification = input(f"Vous ({args.livekit_identity_cli_prompt if args else 'User'} - précision): ")
            elif current_clar_mode == "voice":
                print("Veuillez fournir votre précision oralement:")
                async def get_clar_input():
                    async for text_res in asr_service_global.listen_for_speech(): return text_res
                    return None
                user_clarification = asyncio.run(get_clar_input())
                if not user_clarification or user_clarification.startswith("[ASR_"):
                    print("Agent: Non compris. Essayez texte?"); user_clarification = None
            if not user_clarification and (current_clar_mode == "text" or (livekit_room_instance and not user_clarification)):
                 user_clarification = input(f"Vous (précision texte): ")

            if user_clarification:
                log.info("User provided clarification.", clarification_text=user_clarification)
                current_conversation_history.append({'role': 'user', 'parts': [{'text': user_clarification}]})
                # User-facing print, keep: print("Agent (ARTEX): ...pense (avec précision)...")
                log.info("Agent thinking (with clarification)...")
                clar_response_obj = asyncio.run(generate_agent_response(current_conversation_history))
                final_text = ""
                if isinstance(clar_response_obj, str): final_text = clar_response_obj
                elif clar_response_obj.text: final_text = clar_response_obj.text
                else: final_text = "[GEMINI_NO_TEXT_POST_CLARIFY]"; log.warn("Gemini returned no text after clarification.")

                if final_text.startswith("[HANDOFF]"):
                    # User-facing print, keep:
                    print(f"Agent: {final_text}"); speak_text_output(final_text)
                    log.info("Conversation ended due to HANDOFF after clarification.", handoff_message=final_text)
                    break
                elif final_text.startswith("[CLARIFY]"):
                    # User-facing print, keep:
                    print(f"Agent: Encore besoin de détails, transfert."); speak_text_output("Transfert conseiller.")
                    log.info("Further clarification needed, initiating handoff.", agent_message=final_text)
                    break
                else:
                    # User-facing print, keep:
                    print(f"Agent (ARTEX) (texte): {final_text}"); speak_text_output(final_text)
                current_conversation_history = []
            else:
                no_clar_msg="Agent (ARTEX): Pas de précision."
                # User-facing print, keep:
                print(no_clar_msg); speak_text_output(no_clar_msg)
                log.info("User provided no clarification.")
                current_conversation_history = []
        else:
            # User-facing print, keep:
            print(f"Agent (ARTEX) (texte): {agent_response}"); speak_text_output(agent_response)
            current_conversation_history.append({'role': 'model', 'parts': [{'text': agent_response}]})

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ARTEX ASSURANCES AI Agent")
    parser.add_argument("--livekit-room", type=str, help="Name of the LiveKit room to join.")
    parser.add_argument("--livekit-identity", type=str, default="artex_agent_poc", help="Participant identity for LiveKit.")
    parser.add_argument("--livekit-identity-cli-prompt", type=str, default="LiveKit User", help="Prompt name for CLI input when in LiveKit mode.")
    parser.add_argument("--mic-index", type=int, default=None, help="Device index of the microphone to use for SpeechRecognition.")
    args = parser.parse_args()

    print("Bonjour! Je suis l'assistant IA d'ARTEX ASSURANCES. Comment puis-je vous aider?")
    # User-facing prints, keep:
    print("Bonjour! Je suis l'assistant IA d'ARTEX ASSURANCES. Comment puis-je vous aider?")
    print("==================================================================================")

    _pygame_mixer_initialized = False
    try:
        log.info("CLI Agent starting...")
        configure_services()
        asyncio.run(main_async_logic())
    except ValueError as ve:
        log.error("Configuration error in CLI agent.", error_str=str(ve), exc_info=True)
        print(f"Erreur de configuration: {ve}") # User-facing
    except KeyboardInterrupt:
        log.info("CLI Agent interrupted by user (KeyboardInterrupt).")
        print("\nAu revoir!") # User-facing
    except Exception as e:
        log.critical("Unhandled exception in CLI agent main loop.", error_str=str(e), exc_info=True)
        print(f"Une erreur inattendue est survenue: {e}") # User-facing
    finally:
        log.info("CLI Agent shutting down...")
        if livekit_event_handler_task and not livekit_event_handler_task.done():
            log.info("Cancelling LiveKit event handler task...")
            livekit_event_handler_task.cancel()
            try: asyncio.run(asyncio.sleep(0.1)) # Allow cancellation to propagate
            except RuntimeError as r_err:
                log.warn("RuntimeError during LiveKit task cancellation sleep (likely event loop closed).", error_str=str(r_err))
            log.info("LiveKit event handler task cancelled.")
        if livekit_room_instance and hasattr(livekit_room_instance, 'connection_state') and livekit_room_instance.connection_state == "connected": # Check connection_state if available
            log.info("Disconnecting from LiveKit room...")
            try:
                asyncio.run(livekit_room_instance.disconnect())
                log.info("LiveKit room disconnected.")
            except Exception as lk_disc_err:
                log.error("Error disconnecting LiveKit room.", error_str=str(lk_disc_err), exc_info=True)
        if livekit_room_service_client and hasattr(livekit_room_service_client, 'close'):
            log.info("Closing LiveKit service client...")
            try:
                asyncio.run(livekit_room_service_client.close())
                log.info("LiveKit service client closed.")
            except Exception as lk_close_err:
                log.error("Error closing LiveKit service client.", error_str=str(lk_close_err), exc_info=True)

        if _pygame_mixer_initialized:
            pygame.mixer.quit()
            log.info("Pygame mixer quit.")
        pygame.quit()
        log.info("Pygame quit. Application terminée.")
        # User-facing print, keep:
        print("Application terminée.")
