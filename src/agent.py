# Standard library imports
import os
import sys
import asyncio
import tempfile
import re # Add this import
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
from pathlib import Path # For TTSService path operations

# Local application imports
import src.database as database
from src.database_repositories import ContratRepository, SinistreArthexRepository
import src.livekit_integration as livekit_integration
from src.gemini_client import GeminiClient
from src.gemini_tools import ARTEX_AGENT_TOOLS # Used by AgentService, loaded by main.py, direct use here might be removed
from src.asr import ASRService
from src.tts import TTSService
from .agent_service import AgentService # Import AgentService
from typing import Optional, List, Dict, Any, Tuple # Added Tuple

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

MAX_PROMPT_FILE_SIZE_BYTES = 10 * 1024  # 10KB limit
PLACEHOLDER_REGEX = re.compile(r"\b(TODO|\.\.\.|lorem ipsum|PLACEHOLDER|FIXME)\b", re.IGNORECASE)

def load_prompt(file_name: str, default_prompt: str = DEFAULT_SYSTEM_PROMPT) -> str:
    prompt_dir = os.path.join(os.path.dirname(__file__), '..', 'prompts')
    file_path = os.path.join(prompt_dir, file_name)

    # print(f"DEBUG: Attempting to load prompt from: {file_path}", file=sys.stderr) # For debugging this function

    try:
        # 1. Check for file existence first
        if not os.path.exists(file_path):
            print(f"CRITICAL WARNING: Prompt file {file_path} not found! Using default system prompt. THIS IS A CONFIGURATION ISSUE.", file=sys.stderr)
            return default_prompt

        # 2. Check file size
        file_size = os.path.getsize(file_path)
        if file_size > MAX_PROMPT_FILE_SIZE_BYTES:
            print(f"CRITICAL WARNING: Prompt file {file_path} exceeds size limit ({file_size}b > {MAX_PROMPT_FILE_SIZE_BYTES}b). Using default system prompt.", file=sys.stderr)
            return default_prompt

        # 3. Read file content (with encoding check)
        content = ""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
        except UnicodeDecodeError as ude:
            print(f"CRITICAL WARNING: Prompt file {file_path} has encoding issues (not valid UTF-8): {ude}. Using default system prompt.", file=sys.stderr)
            return default_prompt
        except Exception as e_read: # Catch other read errors
            print(f"ERROR: Error reading prompt file {file_path}: {e_read}. Using default system prompt.", file=sys.stderr)
            return default_prompt

        # 4. Check if file is empty after stripping
        if not content:
            print(f"CRITICAL WARNING: Prompt file {file_path} is empty after stripping whitespace. Using default system prompt.", file=sys.stderr)
            return default_prompt

        # 5. Check for placeholder tokens
        if PLACEHOLDER_REGEX.search(content):
            print(f"CRITICAL WARNING: Prompt file {file_path} appears to contain placeholder tokens (e.g., TODO, ...). Using default system prompt.", file=sys.stderr)
            return default_prompt

        return content

    except Exception as e: # Catch-all for other unexpected errors during checks (e.g., os.path.getsize error)
        print(f"ERROR: Unexpected error during prompt loading for {file_path}: {e}. Using default system prompt.", file=sys.stderr)
        return default_prompt

# Existing global ARTEX_SYSTEM_PROMPT initialization uses the updated load_prompt:
ARTEX_SYSTEM_PROMPT = load_prompt("system_context.txt")
# The if not ARTEX_SYSTEM_PROMPT check is removed as load_prompt now always returns a string.

# --- Global Instances ---
db_engine = None
livekit_room_service_client = None
livekit_room_instance = None
livekit_event_handler_task = None
gemini_chat_client: Optional[GeminiClient] = None # This will be used to init AgentService
agent_service_instance: Optional[AgentService] = None # Global instance for CLI
asr_service_global: Optional[ASRService] = None
tts_service_global: Optional[TTSService] = None
_pygame_mixer_initialized = False
args = None
input_mode = "voice"

# CLI specific session/conversation tracking
cli_session_id = f"cli_session_{uuid.uuid4().hex[:8]}"
cli_conversation_id: Optional[str] = None

def configure_services():
    global db_engine, livekit_room_service_client, gemini_chat_client, asr_service_global, tts_service_global, agent_service_instance
    log.info("Configuring services for CLI agent...")

    # Initialize GeminiClient first as AgentService depends on it
    if gemini_chat_client is None:
        try:
            gemini_chat_client = GeminiClient() # Tools are configured inside GeminiClient or passed at call time
            log.info("GeminiClient initialized successfully for CLI.")
        except ValueError as ve: # Catch specific API key error from GeminiClient
            log.critical(f"Failed to initialize GeminiClient: {ve}", exc_info=True)
            raise SystemExit(f"Erreur critique: {ve}. Vérifiez GEMINI_API_KEY.") # Exit if Gemini can't init
        except Exception as e:
            log.critical("An unexpected error occurred during GeminiClient initialization.", error_str=str(e), exc_info=True)
            raise SystemExit("Erreur critique inattendue lors de l'initialisation de Gemini.")


    # Initialize AgentService
    if agent_service_instance is None and gemini_chat_client:
        try:
            # ARTEX_SYSTEM_PROMPT and ARGO_AGENT_TOOLS are loaded at module level
            agent_service_instance = AgentService(
                gemini_client_instance=gemini_chat_client,
                system_prompt_text=ARTEX_SYSTEM_PROMPT,
                artex_agent_tools_list=ARTEX_AGENT_TOOLS
            )
            log.info("AgentService initialized successfully for CLI.")
        except Exception as e:
            log.critical("Failed to initialize AgentService for CLI.", error_str=str(e), exc_info=True)
            # Depending on how critical AgentService is, you might raise an error or allow degraded mode
            # For now, assume it's critical for CLI to function.
            raise SystemExit("Erreur critique: Impossible d'initialiser AgentService.")


    if db_engine is None: # db_engine is used by AgentService's _execute_function_call via AsyncSessionFactory
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
    log.info("Service configuration finished for CLI.")

# The old generate_agent_response function is removed as its logic is now in AgentService.

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

    # --- OLD LiveKit PoC (Python Server SDK as Participant) ---
    # The following block for LiveKit CLI mode uses functions from livekit_integration.py
    # (e.g., join_room_and_publish_audio) which are part of an older Proof-of-Concept
    # that uses the LiveKit Python Server SDK to simulate a participant.
    # This is DEPRECATED for actual client-side RTC interaction and will be replaced
    # by using the LiveKitParticipantHandler (gRPC based) in future refactoring
    # for a more robust LiveKit client implementation.
    if args and args.livekit_room:
        if not livekit_room_service_client:
            log.error("LiveKit RoomServiceClient not initialized. Cannot join room for OLD PoC mode.")
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
    global input_mode, args, agent_service_instance, cli_session_id, cli_conversation_id

    if not agent_service_instance:
        log.critical("AgentService not initialized. CLI loop cannot function.")
        print("Erreur critique: Le service agent n'est pas disponible. L'application va se terminer.")
        return

    log.info("Starting CLI conversation loop.", livekit_mode=(livekit_room_instance is not None), session_id=cli_session_id)

    if not livekit_room_instance:
        print("Dites quelque chose (ou tapez 'texte', 'exit'/'quit').")
        if input_mode == "voice": print("Vous pouvez aussi taper 'texte' pour passer en mode saisie manuelle.")
    else:
        print(f"Mode LiveKit actif. Tapez messages pour '{args.livekit_identity_cli_prompt}'. Tapez 'exit' ou 'quit' pour terminer.")

    # current_conversation_history is now managed by AgentService.
    # CLI loop only needs to manage the current conversation_id.

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
            print("Agent (ARTEX): Demande vide."); continue # User-facing, keep

        log.info("Agent thinking...") # Internal log, keep
        print("Agent (ARTEX): ...pense...") # User-facing, keep

        # Call AgentService to get the reply
        agent_response_text, new_cli_conv_id, _ = asyncio.run(
            agent_service_instance.get_reply(
                session_id=cli_session_id,
                user_message=user_input,
                conversation_id=cli_conversation_id # Pass current conv ID, will be updated
            )
        )
        cli_conversation_id = new_cli_conv_id # Update CLI's conversation ID

        # Handle [CLARIFY] and [HANDOFF] tags from AgentService response
        if agent_response_text.startswith("[HANDOFF]"):
            handoff_msg = agent_response_text.replace("[HANDOFF]", "").strip() or "Je vous mets en relation avec un conseiller."
            print(f"Agent (ARTEX): {handoff_msg}"); speak_text_output(handoff_msg) # User-facing
            log.info("Conversation ended due to HANDOFF signal from AgentService.", handoff_message=handoff_msg)
            print("Conversation terminée (handoff)."); break # User-facing

        elif agent_response_text.startswith("[CLARIFY]"):
            clarify_q = agent_response_text.replace("[CLARIFY]", "").strip()
            print(f"Agent (ARTEX) précisions: {clarify_q}"); speak_text_output(clarify_q) # User-facing
            log.info("Clarification requested by AgentService.", question=clarify_q)

            user_clarification = None
            current_clar_mode = input_mode # Store current mode before potentially changing
            if livekit_room_instance:
                 print("Clarification (LiveKit - Sim):"); user_clarification = input(f"Vous ({args.livekit_identity_cli_prompt if args else 'User'} - précision): ")
            elif current_clar_mode == "voice":
                print("Veuillez fournir votre précision oralement:")
                async def get_clar_input_clarify():
                    async for text_res in asr_service_global.listen_for_speech(): return text_res
                    return None
                user_clarification = asyncio.run(get_clar_input_clarify())
                if not user_clarification or user_clarification.startswith("[ASR_"):
                    print("Agent: Non compris. Essayez texte?"); user_clarification = None
            if not user_clarification and (current_clar_mode == "text" or (livekit_room_instance and not user_clarification)):
                 user_clarification = input(f"Vous (précision texte): ")

            if user_clarification:
                log.info("User provided clarification to CLI.", clarification_text=user_clarification)
                # Send this clarification back through AgentService
                print("Agent (ARTEX): ...pense (avec précision)...") # User-facing
                agent_response_text, new_cli_conv_id, _ = asyncio.run(
                    agent_service_instance.get_reply(
                        session_id=cli_session_id,
                        user_message=user_clarification, # Send clarification as new user message
                        conversation_id=cli_conversation_id # Continue the same conversation
                    )
                )
                cli_conversation_id = new_cli_conv_id

                # Handle response after clarification (could be another clarify, handoff, or final answer)
                if agent_response_text.startswith("[HANDOFF]"):
                    handoff_msg_clar = agent_response_text.replace("[HANDOFF]", "").strip() or "Je vous mets en relation."
                    print(f"Agent (ARTEX): {handoff_msg_clar}"); speak_text_output(handoff_msg_clar)
                    log.info("HANDOFF after clarification.", message=handoff_msg_clar)
                    break
                elif agent_response_text.startswith("[CLARIFY]"):
                    clarify_q_again = agent_response_text.replace("[CLARIFY]", "").strip()
                    print(f"Agent (ARTEX): Encore besoin de détails: {clarify_q_again}. Transfert conseiller.");
                    speak_text_output(f"Encore besoin de détails: {clarify_q_again}. Je vous suggère de parler à un conseiller.")
                    log.info("Further CLARIFY needed, treating as HANDOFF for CLI.", question=clarify_q_again)
                    break
                else:
                    print(f"Agent (ARTEX) (texte): {agent_response_text}"); speak_text_output(agent_response_text)
            else: # No clarification provided
                no_clar_msg="Agent (ARTEX): Pas de précision fournie."
                print(no_clar_msg); speak_text_output(no_clar_msg)
                log.info("User provided no clarification in CLI.")
                # Reset conversation ID if desired, or let AgentService handle history as is
                # cli_conversation_id = None # Example: force new conversation next time
        else: # Direct response from AgentService
            print(f"Agent (ARTEX) (texte): {agent_response_text}"); speak_text_output(agent_response_text)

        # History management is now inside AgentService.
        # No need for current_conversation_history.append here for the CLI's own tracking,
        # unless it's used for display purposes not covered by AgentService's returned history (which we ignore with `_`).

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
